#!/usr/bin/env bash
# Live checks of the upstream Kubernetes MCP server and the Vyom MCP host on Kind.
# Needs scripts/vyom-up.sh to have run. Opens a localhost-only port-forward for its duration.
#   KUBE_CONTEXT  kubectl context (default: kind-vyom)
#   MCP_PORT      local port for the forward (default: 18443)
# Writes short-lived test tokens under .local/ (ignored by Git) and removes them on exit.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export KUBE_CONTEXT="${KUBE_CONTEXT:-kind-vyom}"
port="${MCP_PORT:-18443}"
export VYOM_LOCAL="$root/.local"
export VYOM_MCP_URL="https://127.0.0.1:$port/mcp"
ca="$VYOM_LOCAL/mcp-tls/tls.crt"
sa=system:serviceaccount:vyom:kubernetes-mcp

k() { kubectl --context "$KUBE_CONTEXT" "$@"; }
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*" >&2; exit 1; }

for tool in kubectl curl uv; do
  command -v "$tool" >/dev/null || fail "missing required tool: $tool"
done
[[ -s "$ca" ]] || fail "no endpoint certificate; run scripts/vyom-up.sh first"

tokens=(mcp-token mcp-token-wrong-audience mcp-token-other-identity)
cleanup() {
  [[ -n "${forward:-}" ]] && kill "$forward" 2>/dev/null || true
  for name in "${tokens[@]}"; do rm -f "${VYOM_LOCAL:?}/${name:?}"; done
}
trap cleanup EXIT

# -- Deployment facts ----------------------------------------------------------------------
images="$(k -n vyom get deployment kubernetes-mcp -o jsonpath='{.spec.template.spec.containers[*].image}')"
for image in $images; do [[ "$image" == *@sha256:* ]] || fail "image not pinned by digest: $image"; done
pass "both images pinned by digest"
[[ "$(k -n vyom get service kubernetes-mcp -o jsonpath='{.spec.type}')" == ClusterIP ]] ||
  fail "Service is not ClusterIP"
[[ -z "$(k get ingress -A -o name)" ]] || fail "an Ingress exists"
pass "Service is ClusterIP; no Ingress in the cluster"

can() { k auth can-i --as="$sa" "$@" 2>/dev/null || true; }
[[ "$(can list pods -n demo)" == yes ]] || fail "server identity cannot list demo pods"
denied=(
  "list pods -n kube-system" "list pods -A" "get pods -n demo" "delete pods -n demo"
  "create pods -n demo" "create pods/exec -n demo" "get pods/log -n demo"
  "get secrets -n demo" "list secrets -n vyom" "list nodes"
)
for request in "${denied[@]}"; do
  # shellcheck disable=SC2086
  [[ "$(can $request)" == no ]] || fail "server identity is allowed: $request"
done
pass "server identity may list pods in demo and is denied ${#denied[@]} other requests (RBAC)"
[[ "$(k auth can-i --as=system:serviceaccount:vyom:vyom-api list pods -n demo 2>/dev/null || true)" == no ]] ||
  fail "the backend identity can read pods directly"
pass "the backend identity has no Kubernetes read access of its own"

# -- Port-forward and tokens ---------------------------------------------------------------
# Started directly, not through k(), so that $! is kubectl itself and cleanup stops it.
kubectl --context "$KUBE_CONTEXT" -n vyom port-forward --address 127.0.0.1 \
  service/kubernetes-mcp "$port:8443" >/dev/null 2>&1 &
forward=$!
for _ in $(seq 1 40); do
  curl --silent --cacert "$ca" --max-time 2 -o /dev/null "https://127.0.0.1:$port/healthz" && break
  sleep 0.5
done
(
  umask 077
  k -n vyom create token vyom-api --audience vyom-mcp --duration 10m >"$VYOM_LOCAL/mcp-token"
  k -n vyom create token vyom-api --duration 10m >"$VYOM_LOCAL/mcp-token-wrong-audience"
  k -n vyom create token default --audience vyom-mcp --duration 10m >"$VYOM_LOCAL/mcp-token-other-identity"
)

status() { # status <token file or ""> -> HTTP status of an initialize request
  local auth=()
  [[ -n "$1" ]] && auth=(-H "Authorization: Bearer $(cat "$VYOM_LOCAL/$1")")
  curl --silent --cacert "$ca" --max-time 15 -o /dev/null -w '%{http_code}' -X POST \
    "$VYOM_MCP_URL" -H 'content-type: application/json' \
    -H 'accept: application/json, text/event-stream' "${auth[@]}" \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"vyom-check","version":"0"}}}'
}
[[ "$(status "")" == 401 ]] || fail "a caller without a credential was not refused"
[[ "$(status mcp-token-wrong-audience)" == 401 ]] || fail "a Kubernetes-audience token was accepted"
[[ "$(status mcp-token-other-identity)" == 403 ]] || fail "an ungranted identity was accepted"
[[ "$(status mcp-token)" == 200 ]] || fail "the backend identity was refused"
pass "endpoint: no credential 401, Kubernetes-audience token 401, ungranted identity 403, backend token 200"

api="$(k config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
code="$(curl --silent --insecure --max-time 10 -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer $(cat "$VYOM_LOCAL/mcp-token")" "$api/api/v1/namespaces/demo/pods")"
[[ "$code" == 401 ]] || fail "the endpoint token was accepted by the Kubernetes API ($code)"
pass "the token the backend presents is rejected by the Kubernetes API itself (401)"

# -- Host checks ---------------------------------------------------------------------------
VYOM_CLUSTER_UID="$(k get namespace kube-system -o jsonpath='{.metadata.uid}')"
export VYOM_CLUSTER_UID
uv run --project "$root/backend" --locked python "$root/scripts/mcp_live_check.py"

# -- Upstream logs -------------------------------------------------------------------------
logs="$(k -n vyom logs deployment/kubernetes-mcp --all-containers --since=10m)"
for needle in "$(cat "$VYOM_LOCAL/mcp-token")" vyom-demo-literal-env-value "web-" "broken-" labelSelector; do
  if grep --quiet --fixed-strings -- "$needle" <<<"$logs"; then
    fail "upstream logs contain a payload value"
  fi
done
pass "upstream server and proxy logs ($(wc -l <<<"$logs") recent lines) hold no token, env value, pod name or argument"
echo "all MCP checks passed"
