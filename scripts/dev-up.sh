#!/usr/bin/env bash
# Run the backend on this machine wired to the Kind cluster, for development: the agent
# through the Kubernetes MCP endpoint, and the direct pod collector against the API server.
# Needs scripts/vyom-up.sh to have run. Opens a localhost-only port-forward to the MCP
# endpoint, writes two one-hour tokens (MCP endpoint, collector), the cluster CA and an
# operator configuration under .local/ (ignored by Git), and serves the API on
# 127.0.0.1:8000 until interrupted. Start the UI separately with `npm run dev` in frontend/.
# The model key comes from one of, in this order:
#   OPENROUTER_API_KEY   environment variable in the terminal that runs this script
#   VYOM_MODEL_KEY_FILE  file holding the key (default: .local/model-api-key, mode 600)
# Other settings:
#   KUBE_CONTEXT (kind-vyom)  MCP_PORT (18443)  VYOM_NAMESPACE (demo)
#   VYOM_MODEL_PROVIDER (openrouter)  VYOM_MODEL_BASE_URL (https://openrouter.ai/api/v1)
#   VYOM_MODEL (anthropic/claude-haiku-5.5)
# Without a key the API still starts; chat then reports that the model credential is missing.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
context="${KUBE_CONTEXT:-kind-vyom}"
[[ "$context" == kind-* ]] || { echo "KUBE_CONTEXT must name a local kind-* context" >&2; exit 1; }
port="${MCP_PORT:-18443}"
local_dir="$root/.local"
ca="$local_dir/mcp-tls/tls.crt"
token="$local_dir/dev-mcp-token"
collector_token="$local_dir/dev-collector-token"
api_ca="$local_dir/dev-kubernetes-ca.crt"
key_file="${VYOM_MODEL_KEY_FILE:-$local_dir/model-api-key}"
k() { kubectl --context "$context" "$@"; }

for tool in kubectl curl uv; do
  command -v "$tool" >/dev/null || { echo "missing required tool: $tool" >&2; exit 1; }
done
[[ -s "$ca" ]] || { echo "no endpoint certificate; run scripts/vyom-up.sh first" >&2; exit 1; }

cleanup() {
  [[ -n "${forward:-}" ]] && kill "$forward" 2>/dev/null || true
  rm -f "$token" "$collector_token"
}
trap cleanup EXIT

# Started directly, not through k(), so that $! is kubectl itself and cleanup stops it.
kubectl --context "$context" -n vyom port-forward --address 127.0.0.1 \
  service/kubernetes-mcp "$port:8443" >/dev/null 2>&1 &
forward=$!
for _ in $(seq 1 40); do
  curl --silent --cacert "$ca" --max-time 2 -o /dev/null "https://127.0.0.1:$port/healthz" && break
  sleep 0.5
done
(
  umask 077
  k -n vyom create token vyom-api --audience vyom-mcp --duration 1h >"$token"
  # The collector reads the Kubernetes API as its own ServiceAccount, not through MCP.
  k -n vyom create token vyom-collector --duration 1h >"$collector_token"
)
k config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' |
  base64 -d >"$api_ca"
api_server="$(k config view --minify -o jsonpath='{.clusters[0].cluster.server}')"

if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
  credential_ref=env:OPENROUTER_API_KEY
else
  credential_ref="file:$key_file"
  [[ -s "$key_file" ]] || echo "note: no model key at ${key_file#"$root"/}; chat will report a missing credential" >&2
fi

cat >"$local_dir/operator.json" <<JSON
{
  "context": {
    "workspace_id": "ws-local",
    "connection_id": "kind-vyom",
    "cluster_uid": "$(k get namespace kube-system -o jsonpath='{.metadata.uid}')",
    "namespace": "${VYOM_NAMESPACE:-demo}"
  },
  "mcp_servers": [
    {
      "id": "kubernetes",
      "connection_id": "kind-vyom",
      "url": "https://127.0.0.1:$port/mcp",
      "ca_file": "$ca",
      "credential_ref": "file:$token",
      "enabled_tools": ["pods_list_in_namespace"]
    }
  ],
  "model": {
    "provider": "${VYOM_MODEL_PROVIDER:-openrouter}",
    "base_url": "${VYOM_MODEL_BASE_URL:-https://openrouter.ai/api/v1}",
    "model": "${VYOM_MODEL:-anthropic/claude-haiku-5.5}",
    "credential_ref": "$credential_ref"
  },
  "kubernetes": {
    "connection_id": "kind-vyom",
    "url": "$api_server",
    "ca_file": "$api_ca",
    "credential_ref": "file:$collector_token"
  }
}
JSON

echo "API on http://127.0.0.1:8000 (scope: namespace ${VYOM_NAMESPACE:-demo}); the two tokens last one hour"
VYOM_MODE=development VYOM_CONFIG="$local_dir/operator.json" uv run --project "$root/backend" --locked \
  uvicorn vyom.api.app:app --host 127.0.0.1 --port 8000
