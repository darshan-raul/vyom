#!/usr/bin/env bash
# Install or upgrade the pinned S1 observability stack. Safe to re-run.
#   KUBE_CONTEXT  kubectl/helm context (default: kind-vyom)
# Chart pins: deploy/observability/charts.lock. Grafana's admin password is generated once
# into .local/grafana-admin-password (ignored by Git) and injected as a Secret.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
obs="$root/deploy/observability"
cache="$root/.local/charts"
context="${KUBE_CONTEXT:-kind-vyom}"
namespace=observability
password_file="$root/.local/grafana-admin-password"

profile="${VYOM_TELEMETRY:-metrics}"
case "$profile" in
  metrics|full) ;;
  *) echo "VYOM_TELEMETRY must be metrics or full (none needs no telemetry install)" >&2; exit 1 ;;
esac

k() { kubectl --context "$context" "$@"; }

for tool in kubectl helm curl sha256sum openssl; do
  command -v "$tool" >/dev/null || { echo "missing required tool: $tool" >&2; exit 1; }
done
k version -o json >/dev/null || { echo "cannot reach cluster for context $context" >&2; exit 1; }

# `vyom` exists up front so the collector's namespaced discovery Role can be created there.
for ns in "$namespace" vyom; do
  k create namespace "$ns" --dry-run=client -o yaml | k apply -f - >/dev/null
done

mkdir -p "$cache"
if [[ "$profile" == full ]]; then
if [[ ! -s "$password_file" ]]; then
  (umask 077 && openssl rand -hex 24 | tr -d '\n' >"$password_file")
  echo "generated Grafana admin password in ${password_file#"$root"/}"
fi
k -n "$namespace" create secret generic grafana-admin \
  --from-literal=admin-user=admin --from-file=admin-password="$password_file" \
  --dry-run=client -o yaml | k apply -f - >/dev/null

# Dashboards are provisioned by Grafana's sidecar from labelled ConfigMaps.
k -n "$namespace" create configmap vyom-dashboards --from-file="$obs/dashboards" \
  --dry-run=client -o yaml |
  k label --local -f - grafana_dashboard=1 -o yaml | k apply --server-side -f - >/dev/null

fi

install() {
  local release=$1 chart=$2 version=$3 url=$4 sha=$5
  shift 5
  local archive="$cache/$chart-$version.tgz"
  if ! echo "$sha  $archive" | sha256sum --check --status 2>/dev/null; then
    echo "fetching $chart $version"
    curl --fail --silent --show-error --location --retry 5 --retry-all-errors \
      --max-time 180 --output "$archive" "$url"
    echo "$sha  $archive" | sha256sum --check --status ||
      { echo "checksum mismatch for $archive" >&2; exit 1; }
  fi
  echo "installing $release ($chart $version)"
  helm --kube-context "$context" upgrade --install "$release" "$archive" \
    --namespace "$namespace" --values "$obs/$release.values.yaml" \
    --wait --timeout 15m "$@" >/dev/null
}

while read -r release chart version url sha; do
  [[ -z "$release" || "$release" == \#* ]] && continue
  [[ "$profile" == metrics && "$release" != kube-prometheus-stack ]] && continue
  extra=()
  [[ "$profile" == metrics ]] && extra=(--set grafana.enabled=false)
  [[ "$release" == alloy ]] && extra=(--set-file "alloy.configMap.content=$obs/config.alloy")
  install "$release" "$chart" "$version" "$url" "$sha" "${extra[@]}"
done <"$obs/charts.lock"

k -n "$namespace" get pods
if [[ "$profile" == full ]]; then
cat <<MSG

Grafana (localhost only):
  kubectl --context $context -n $namespace port-forward svc/grafana 3000:80 --address 127.0.0.1
  user: admin   password: contents of ${password_file#"$root"/}
MSG

else
  echo "Prometheus installed without Grafana, Loki, Tempo or Alloy. Existing optional releases are not uninstalled."
fi
