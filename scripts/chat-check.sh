#!/usr/bin/env bash
# Live gate for S1.5: a real question through the API, the graph, the configured model and
# the upstream Kubernetes MCP server on Kind, plus the failure paths.
# Needs scripts/mcp-up.sh to have run. Sends about ten small requests to the model provider,
# which costs a little. Opens a localhost-only port-forward for its duration.
# The model key comes from one of, in this order:
#   OPENROUTER_API_KEY   environment variable in the terminal that runs this script
#   VYOM_MODEL_KEY_FILE  file holding the key (default: .local/model-api-key, mode 600)
# Other settings: KUBE_CONTEXT (kind-vyom), MCP_PORT (18443), VYOM_MODEL_PROVIDER,
# VYOM_MODEL_BASE_URL, VYOM_MODEL (defaults as in scripts/model-check.sh).
# Writes a short-lived endpoint token under .local/ (ignored by Git) and removes it on exit.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export KUBE_CONTEXT="${KUBE_CONTEXT:-kind-vyom}"
port="${MCP_PORT:-18443}"
export VYOM_LOCAL="$root/.local"
export VYOM_MCP_URL="https://127.0.0.1:$port/mcp"
export VYOM_MCP_TOKEN_FILE="$VYOM_LOCAL/chat-check-mcp-token"
export VYOM_MODEL_KEY_FILE="${VYOM_MODEL_KEY_FILE:-$VYOM_LOCAL/model-api-key}"
export VYOM_MODEL_PROVIDER="${VYOM_MODEL_PROVIDER:-openrouter}"
export VYOM_MODEL_BASE_URL="${VYOM_MODEL_BASE_URL:-https://openrouter.ai/api/v1}"
export VYOM_MODEL="${VYOM_MODEL:-anthropic/claude-haiku-5.5}"
ca="$VYOM_LOCAL/mcp-tls/tls.crt"

k() { kubectl --context "$KUBE_CONTEXT" "$@"; }
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*" >&2; exit 1; }

for tool in kubectl curl uv git; do
  command -v "$tool" >/dev/null || fail "missing required tool: $tool"
done
[[ -s "$ca" ]] || fail "no endpoint certificate; run scripts/mcp-up.sh first"
if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
  export VYOM_MODEL_CREDENTIAL_REF=env:OPENROUTER_API_KEY
  pass "key taken from the OPENROUTER_API_KEY environment variable"
else
  [[ -s "$VYOM_MODEL_KEY_FILE" ]] ||
    fail "no key: export OPENROUTER_API_KEY in this terminal, or create $VYOM_MODEL_KEY_FILE with mode 600 (see README)"
  [[ "$(stat -c %a "$VYOM_MODEL_KEY_FILE")" == 600 ]] ||
    fail "the key file must have mode 600: chmod 600 $VYOM_MODEL_KEY_FILE"
  git -C "$root" check-ignore --quiet "$VYOM_MODEL_KEY_FILE" ||
    fail "the key file is not ignored by Git; keep it under .local/"
  export VYOM_MODEL_CREDENTIAL_REF="file:$VYOM_MODEL_KEY_FILE"
  pass "key file present, mode 600, ignored by Git"
fi

cleanup() {
  [[ -n "${forward:-}" ]] && kill "$forward" 2>/dev/null || true
  rm -f "$VYOM_MCP_TOKEN_FILE"
}
trap cleanup EXIT

# Started directly, not through k(), so that $! is kubectl itself and cleanup stops it.
kubectl --context "$KUBE_CONTEXT" -n vyom port-forward --address 127.0.0.1 \
  service/kubernetes-mcp "$port:8443" >/dev/null 2>&1 &
forward=$!
for _ in $(seq 1 40); do
  curl --silent --cacert "$ca" --max-time 2 -o /dev/null "https://127.0.0.1:$port/healthz" && break
  sleep 0.5
done
(umask 077 && k -n vyom create token vyom-api --audience vyom-mcp --duration 15m >"$VYOM_MCP_TOKEN_FILE")
VYOM_CLUSTER_UID="$(k get namespace kube-system -o jsonpath='{.metadata.uid}')"
export VYOM_CLUSTER_UID

before="$(k -n demo get pods -o jsonpath='{range .items[*]}{.metadata.uid}{"\n"}{end}' | sort)"
uv run --project "$root/backend" --locked python "$root/scripts/chat_live_check.py"
after="$(k -n demo get pods -o jsonpath='{range .items[*]}{.metadata.uid}{"\n"}{end}' | sort)"
[[ "$before" == "$after" ]] || fail "the demo pods changed during the check"
pass "the demo pods are the same objects after the check: nothing was written"

logs="$(k -n vyom logs deployment/kubernetes-mcp --all-containers --since=10m)"
for needle in "$(cat "$VYOM_MCP_TOKEN_FILE")" vyom-chat-marker vyom-demo-literal-env-value "web-" "broken-"; do
  if grep --quiet --fixed-strings -- "$needle" <<<"$logs"; then
    fail "upstream logs contain a payload value"
  fi
done
pass "upstream server and proxy logs ($(wc -l <<<"$logs") recent lines) hold no token, question, env value or pod name"
echo "all chat checks passed"
