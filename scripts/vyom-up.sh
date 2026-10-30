#!/usr/bin/env bash
# Install or update Vyom on Kind: build the API and UI images, load them into the cluster,
# create the private Secrets, install the one Vyom chart and fill the collector's token.
# Safe to re-run. Create the cluster first with `kind create cluster --config
# deploy/kind/cluster.yaml` (or pass --create-cluster), and run scripts/observability-up.sh
# before this if you want Prometheus to scrape the API and traces to reach Tempo.
#   KUBE_CONTEXT         kubectl/helm context (default: kind-vyom)
#   OPENROUTER_API_KEY   model key, or put it in VYOM_MODEL_KEY_FILE (default .local/model-api-key)
#   VYOM_TELEMETRY       none (default), metrics or full; install matching telemetry first
#   VYOM_MODE            development (default). production makes the API refuse to start.
# Secrets are created from local files and never pass through chart values:
#   kubernetes-mcp-tls   endpoint certificate, generated once into .local/mcp-tls/ (90 days)
#   vyom-model-key       the model provider key (skipped if you have none; chat then says so)
#   vyom-collector-token empty at first; the chart's CronJob keeps a short-lived token in it
# Nothing is exposed outside the cluster; reach the UI with scripts/vyom-forward.sh.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
context="${KUBE_CONTEXT:-kind-vyom}"
[[ "$context" == kind-* ]] || { echo "KUBE_CONTEXT must name a local kind-* context" >&2; exit 1; }
cluster="${context#kind-}"
tls="$root/.local/mcp-tls"
key_file="${VYOM_MODEL_KEY_FILE:-$root/.local/model-api-key}"
pg_password_file="$root/.local/postgres-password"
k() { kubectl --context "$context" "$@"; }

# Explicit profile: never export to an absent trace collector by default.
telemetry="${VYOM_TELEMETRY:-none}"
monitor=false
otlp=""
case "$telemetry" in
  none) ;;
  metrics) monitor=true ;;
  full) monitor=true; otlp=http://alloy.observability.svc:4318 ;;
  *) echo "VYOM_TELEMETRY must be none, metrics or full" >&2; exit 1 ;;
esac

create_cluster=false
[[ "${1:-}" == "--create-cluster" ]] && create_cluster=true

for tool in docker kind kubectl helm openssl sha256sum; do
  command -v "$tool" >/dev/null || { echo "missing required tool: $tool" >&2; exit 1; }
done
if $create_cluster && ! kind get clusters 2>/dev/null | grep -qx "$cluster"; then
  kind create cluster --name "$cluster" --config "$root/deploy/kind/cluster.yaml"
fi
k version -o json >/dev/null || { echo "cannot reach cluster for context $context" >&2; exit 1; }

if $monitor && ! k get crd servicemonitors.monitoring.coreos.com >/dev/null 2>&1; then
  echo "profile $telemetry requires Prometheus; run VYOM_TELEMETRY=$telemetry scripts/observability-up.sh first" >&2
  exit 1
fi

# shellcheck source=../deploy/images.lock
source "$root/deploy/images.lock"

# A tag from the content of the build inputs, so a changed file means a new image and a new
# rollout, and an unchanged tree reuses the loaded image.
digest_of() {
  (cd "$root/$1" && git ls-files -co --exclude-standard -z . | sort -z | xargs -0 sha256sum |
    sha256sum | cut -c1-12)
}
api_tag="$(digest_of backend)"
ui_tag="$(digest_of frontend)"

build() {
  local name=$1 dir=$2 tag=$3
  shift 3
  if ! docker image inspect "vyom/$name:$tag" >/dev/null 2>&1; then
    echo "building vyom/$name:$tag"
    docker build --quiet --tag "vyom/$name:$tag" "$@" "$root/$dir" >/dev/null
  fi
  # `kind load docker-image` can fail with some Docker image stores; an archive always works.
  if ! kind load docker-image --name "$cluster" "vyom/$name:$tag" >/dev/null 2>&1; then
    docker save "vyom/$name:$tag" | kind load image-archive --name "$cluster" /dev/stdin >/dev/null
  fi
}
build api backend "$api_tag" --build-arg "PYTHON_IMAGE=$PYTHON_IMAGE"
build ui frontend "$ui_tag" --build-arg "NODE_IMAGE=$NODE_IMAGE" --build-arg "NGINX_IMAGE=$NGINX_IMAGE"

for ns in vyom demo; do
  k create namespace "$ns" --dry-run=client -o yaml | k apply -f - >/dev/null
done
k apply -f "$root/deploy/kind/demo.yaml" >/dev/null

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

if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
  printf %s "$OPENROUTER_API_KEY" | k -n vyom create secret generic vyom-model-key \
    --from-file=key=/dev/stdin --dry-run=client -o yaml | k apply -f - >/dev/null
elif [[ -s "$key_file" ]]; then
  k -n vyom create secret generic vyom-model-key --from-file=key="$key_file" \
    --dry-run=client -o yaml | k apply -f - >/dev/null
else
  echo "note: no model key (OPENROUTER_API_KEY or ${key_file#"$root"/}); chat will report a missing credential" >&2
fi

# The collector's token Secret exists before the chart so the API pod can mount it; the
# refresher fills it. An existing token is left alone.
k -n vyom get secret vyom-collector-token >/dev/null 2>&1 ||
  k -n vyom create secret generic vyom-collector-token --from-literal=token= >/dev/null

# Postgres credentials live in a Secret created beside the release, never in values.
if [[ ! -s "$pg_password_file" ]]; then
  mkdir -p "$(dirname "$pg_password_file")"
  (umask 077 && openssl rand -hex 24 | tr -d '\n' >"$pg_password_file")
  echo "generated Postgres password in ${pg_password_file#"$root"/}"
fi
pg_password="$(cat "$pg_password_file")"
k -n vyom create secret generic vyom-postgres \
  --from-file=password="$pg_password_file" \
  --from-literal=url="postgresql://vyom:$pg_password@vyom-postgres.vyom.svc:5432/vyom" \
  --dry-run=client -o yaml | k apply -f - >/dev/null

# Alloy collects Vyom's logs through a Role in this namespace that the observability install
# created. If the namespace was deleted and recreated, the Role is gone and logs stop silently.
if [[ "$telemetry" == full ]] && k get namespace observability >/dev/null 2>&1 && ! k -n vyom get role alloy >/dev/null 2>&1; then
  echo "warning: Alloy has no Role in namespace vyom, so Vyom's logs are not collected; re-run scripts/observability-up.sh" >&2
fi

# The MCP pod reads its configuration and certificate at start: roll it only when they change.
checksum="$(cat "$root/deploy/chart/vyom/files/kubernetes-mcp.toml" "$tls/tls.crt" | sha256sum | cut -c1-16)"

helm --kube-context "$context" upgrade --install vyom "$root/deploy/chart/vyom" \
  --namespace vyom --wait --timeout 5m \
  --set "mode=${VYOM_MODE:-development}" \
  --set "context.clusterUid=$(k get namespace kube-system -o jsonpath='{.metadata.uid}')" \
  --set "images.api.tag=$api_tag" --set "images.ui.tag=$ui_tag" \
  --set "mcp.checksum=$checksum" --set "serviceMonitor.enabled=$monitor" \
  --set-string "telemetry.otlpEndpoint=$otlp" >/dev/null

# Run the controlled schema migration Job now that vyom-postgres is ready.
k -n vyom rollout status statefulset/vyom-postgres --timeout=120s >/dev/null
k -n vyom delete job vyom-migrate-run --ignore-not-found >/dev/null
k -n vyom create job vyom-migrate-run --from=cronjob/vyom-migrate >/dev/null
k -n vyom wait --for=condition=complete job/vyom-migrate-run --timeout=120s >/dev/null

# Fill the collector's token now rather than at the next half hour.
k -n vyom delete job vyom-collector-token-initial --ignore-not-found >/dev/null
k -n vyom create job vyom-collector-token-initial --from=cronjob/vyom-collector-token-refresh >/dev/null
k -n vyom wait --for=condition=complete job/vyom-collector-token-initial --timeout=120s >/dev/null

# The kubelet shows a changed Secret inside a running pod after up to about a minute; wait for
# it so the pods view works the moment this script ends. (Later rotations need no wait: a
# token lives an hour and is replaced every half hour.)
for _ in $(seq 60); do
  k -n vyom exec deploy/vyom-api -- test -s /var/run/vyom/collector/token 2>/dev/null && break
  sleep 3
done

k -n vyom exec deploy/vyom-api -- test -s /var/run/vyom/collector/token || {
  echo "collector token has not reached the API pod; retry installation after checking Secret projection" >&2
  exit 1
}

k -n demo rollout status deployment/web --timeout=5m
echo "Vyom is ready in namespace vyom (images vyom/api:$api_tag, vyom/ui:$ui_tag). Open the UI with scripts/vyom-forward.sh"
