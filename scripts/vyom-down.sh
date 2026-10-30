#!/usr/bin/env bash
# Remove Vyom from the cluster: the release, its Secrets, the `demo` namespace and the cluster-
# scoped review role. The namespace `vyom` stays: Alloy's log-discovery Role lives there and
# belongs to the observability stack (scripts/observability-up.sh), which is untouched. With
# --cluster the whole Kind cluster is deleted instead.
#   KUBE_CONTEXT  kubectl context (default: kind-vyom)
set -euo pipefail
context="${KUBE_CONTEXT:-kind-vyom}"
[[ "$context" == kind-* ]] || { echo "KUBE_CONTEXT must name a local kind-* context" >&2; exit 1; }
if [[ "${1:-}" == "--cluster" ]]; then
  kind delete cluster --name "${context#kind-}"
  exit 0
fi
k() { kubectl --context "$context" "$@"; }
helm --kube-context "$context" -n vyom uninstall vyom 2>/dev/null || true
k -n vyom delete job --all --ignore-not-found
k -n vyom delete pvc -l app.kubernetes.io/part-of=vyom --ignore-not-found
k -n vyom delete secret kubernetes-mcp-tls vyom-model-key vyom-collector-token vyom-postgres --ignore-not-found
k delete namespace demo --ignore-not-found
k delete clusterrole,clusterrolebinding vyom-kubernetes-mcp-caller-review --ignore-not-found
echo "Vyom removed (namespace vyom is kept for the observability stack). Local files under .local/ (certificate, keys) are kept."
