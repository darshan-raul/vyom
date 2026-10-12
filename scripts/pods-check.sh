#!/usr/bin/env bash
# Live gate for S1.6: the direct pod view against kubectl on Kind, its independence from
# MCP, and a controlled workload change seen by both the direct view and the MCP path.
# Needs scripts/mcp-up.sh to have run. Scales the demo `web` Deployment to 2 replicas and
# back to 1 (that is this script changing the demo workload with your kubectl access, not
# Vyom). Opens a localhost-only port-forward for its duration.
# With a model key it also asks the agent about the changed workload (two small requests):
#   OPENROUTER_API_KEY   environment variable in the terminal that runs this script
#   VYOM_MODEL_KEY_FILE  file holding the key (default: .local/model-api-key, mode 600)
# Without a key the script stops, unless VYOM_SKIP_MODEL=1: then everything else runs, the
# answer check is reported as NOT RUN and the script ends INCOMPLETE (exit 2), not passed.
# Other settings: KUBE_CONTEXT (kind-vyom), MCP_PORT (18443), VYOM_MODEL_PROVIDER,
# VYOM_MODEL_BASE_URL, VYOM_MODEL (defaults as in scripts/model-check.sh).
# Writes short-lived tokens under .local/ (ignored by Git) and removes them on exit.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export KUBE_CONTEXT="${KUBE_CONTEXT:-kind-vyom}"
port="${MCP_PORT:-18443}"
export VYOM_LOCAL="$root/.local"
export VYOM_MCP_URL="https://127.0.0.1:$port/mcp"
export VYOM_MCP_TOKEN_FILE="$VYOM_LOCAL/pods-check-mcp-token"
export VYOM_COLLECTOR_TOKEN_FILE="$VYOM_LOCAL/pods-check-collector-token"
export VYOM_BAD_TOKEN_FILE="$VYOM_LOCAL/pods-check-bad-token"
export VYOM_KUBERNETES_CA="$VYOM_LOCAL/pods-check-kubernetes-ca.crt"
export VYOM_MODEL_KEY_FILE="${VYOM_MODEL_KEY_FILE:-$VYOM_LOCAL/model-api-key}"
export VYOM_MODEL_PROVIDER="${VYOM_MODEL_PROVIDER:-openrouter}"
export VYOM_MODEL_BASE_URL="${VYOM_MODEL_BASE_URL:-https://openrouter.ai/api/v1}"
export VYOM_MODEL="${VYOM_MODEL:-anthropic/claude-haiku-5.5}"
ca="$VYOM_LOCAL/mcp-tls/tls.crt"
collector=system:serviceaccount:vyom:vyom-collector

k() { kubectl --context "$KUBE_CONTEXT" "$@"; }
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*" >&2; exit 1; }

for tool in kubectl curl uv base64; do
  command -v "$tool" >/dev/null || fail "missing required tool: $tool"
done
[[ -s "$ca" ]] || fail "no endpoint certificate; run scripts/mcp-up.sh first"
k -n vyom get serviceaccount vyom-collector >/dev/null 2>&1 ||
  fail "no collector ServiceAccount; run scripts/mcp-up.sh"

export VYOM_MODEL_CREDENTIAL_REF=""
if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
  export VYOM_MODEL_CREDENTIAL_REF=env:OPENROUTER_API_KEY
elif [[ -s "$VYOM_MODEL_KEY_FILE" ]]; then
  export VYOM_MODEL_CREDENTIAL_REF="file:$VYOM_MODEL_KEY_FILE"
elif [[ "${VYOM_SKIP_MODEL:-}" != 1 ]]; then
  fail "no model key: export OPENROUTER_API_KEY, create $VYOM_MODEL_KEY_FILE, or set VYOM_SKIP_MODEL=1 to run everything except the agent's answer"
fi

cleanup() {
  [[ -n "${forward:-}" ]] && kill "$forward" 2>/dev/null || true
  rm -f "$VYOM_MCP_TOKEN_FILE" "$VYOM_COLLECTOR_TOKEN_FILE" "$VYOM_BAD_TOKEN_FILE" "$VYOM_KUBERNETES_CA"
  k -n demo scale deployment/web --replicas=1 >/dev/null 2>&1 || true
}
trap cleanup EXIT

# -- The collector's identity ---------------------------------------------------------------
can() { k auth can-i --as="$collector" "$@" 2>/dev/null || true; }
[[ "$(can list pods -n demo)" == yes ]] || fail "the collector identity cannot list demo pods"
denied=(
  "list pods -n kube-system" "list pods -A" "get pods -n demo" "watch pods -n demo"
  "delete pods -n demo" "create pods -n demo" "create pods/exec -n demo" "get pods/log -n demo"
  "get secrets -n demo" "list secrets -n vyom" "list nodes"
)
for request in "${denied[@]}"; do
  # shellcheck disable=SC2086
  [[ "$(can $request)" == no ]] || fail "the collector identity is allowed: $request"
done
pass "the collector identity may list pods in demo and is denied ${#denied[@]} other requests (RBAC)"

# -- Port-forward, tokens and the API server's CA ------------------------------------------
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
  k -n vyom create token vyom-api --audience vyom-mcp --duration 15m >"$VYOM_MCP_TOKEN_FILE"
  k -n vyom create token vyom-collector --duration 15m >"$VYOM_COLLECTOR_TOKEN_FILE"
  echo "not-a-valid-token" >"$VYOM_BAD_TOKEN_FILE"
)
k config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' |
  base64 -d >"$VYOM_KUBERNETES_CA"
VYOM_KUBERNETES_URL="$(k config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
VYOM_CLUSTER_UID="$(k get namespace kube-system -o jsonpath='{.metadata.uid}')"
export VYOM_KUBERNETES_URL VYOM_CLUSTER_UID

k -n demo scale deployment/web --replicas=1 >/dev/null
k -n demo rollout status deployment/web --timeout=2m >/dev/null

uv run --project "$root/backend" --locked python "$root/scripts/pods_live_check.py"
echo "all pod view checks passed"
