#!/usr/bin/env bash
# Install or update the pinned upstream Kubernetes MCP server, the direct collector's
# ServiceAccount and the demo workloads. Safe to re-run.
#   KUBE_CONTEXT  kubectl context (default: kind-vyom)
# Pins: the image digests in deploy/kubernetes-mcp/manifests.yaml. Server settings:
# deploy/kubernetes-mcp/config.toml. Nothing is exposed outside the cluster.
# A self-signed endpoint certificate is generated once into .local/mcp-tls/ (ignored by Git);
# tls.crt is what a client trusts, tls.key goes only into the kubernetes-mcp-tls Secret.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
context="${KUBE_CONTEXT:-kind-vyom}"
tls="$root/.local/mcp-tls"
k() { kubectl --context "$context" "$@"; }

for tool in kubectl openssl sha256sum; do
  command -v "$tool" >/dev/null || { echo "missing required tool: $tool" >&2; exit 1; }
done
k version -o json >/dev/null || { echo "cannot reach cluster for context $context" >&2; exit 1; }

k create namespace vyom --dry-run=client -o yaml | k apply -f - >/dev/null
k apply -f "$root/deploy/kind/demo.yaml" >/dev/null
# The direct collector's own identity (S1.6); it does not go through the MCP server.
k apply -f "$root/deploy/collector/rbac.yaml" >/dev/null

if [[ ! -s "$tls/tls.crt" || ! -s "$tls/tls.key" ]]; then
  mkdir -p "$tls"
  (umask 077 && openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
    -days 90 -subj "/CN=kubernetes-mcp.vyom.svc" \
    -addext "subjectAltName=DNS:kubernetes-mcp.vyom.svc,DNS:kubernetes-mcp.vyom.svc.cluster.local,DNS:localhost,IP:127.0.0.1" \
    -keyout "$tls/tls.key" -out "$tls/tls.crt" 2>/dev/null)
  echo "generated the MCP endpoint certificate in ${tls#"$root"/}"
fi
k -n vyom create secret tls kubernetes-mcp-tls --cert="$tls/tls.crt" --key="$tls/tls.key" \
  --dry-run=client -o yaml | k apply -f - >/dev/null

k -n vyom create configmap kubernetes-mcp-config \
  --from-file=config.toml="$root/deploy/kubernetes-mcp/config.toml" \
  --dry-run=client -o yaml | k apply -f - >/dev/null
k apply -f "$root/deploy/kubernetes-mcp/manifests.yaml" >/dev/null
# The server reads its configuration and certificate at start: roll only when they change.
checksum="$(cat "$root/deploy/kubernetes-mcp/config.toml" "$tls/tls.crt" | sha256sum | cut -c1-16)"
k -n vyom patch deployment kubernetes-mcp --type merge --patch \
  "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"vyom.dev/config-checksum\":\"$checksum\"}}}}}" >/dev/null
k -n vyom rollout status deployment/kubernetes-mcp --timeout=5m
k -n demo rollout status deployment/web --timeout=5m
echo "kubernetes-mcp is ready in namespace vyom; demo workloads are in namespace demo"
