#!/usr/bin/env bash
# Read-only checks of the installed observability stack through localhost-bound port-forwards.
# Sends one synthetic span. Exits non-zero on the first failed check.
#   KUBE_CONTEXT  kubectl context (default: kind-vyom)
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
context="${KUBE_CONTEXT:-kind-vyom}"
[[ "$context" == kind-* ]] || { echo "KUBE_CONTEXT must name a local kind-* context" >&2; exit 1; }
password_file="$root/.local/grafana-admin-password"
pids=()
trap 'kill "${pids[@]}" 2>/dev/null || true' EXIT

k() { kubectl --context "$context" -n observability "$@"; }
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*" >&2; exit 1; }
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

forward() { # service, local port, remote port: returns once HTTP answers through the tunnel
  # kubectl directly, not through k(): $! must be kubectl itself so the exit trap stops it.
  kubectl --context "$context" -n observability port-forward "svc/$1" "$2:$3" \
    --address 127.0.0.1 >/dev/null 2>&1 &
  pids+=($!)
  for _ in $(seq 40); do
    [[ "$(code "http://127.0.0.1:$2/")" != 000 ]] && return 0
    sleep 0.5
  done
  fail "port-forward to $1 did not answer"
}

forward kps-prometheus 19090 9090
forward loki 13100 3100
forward tempo 13200 3200
forward grafana 13000 80
forward alloy 14318 4318

# Grafana: private, authenticated, provisioned.
[[ "$(code http://127.0.0.1:13000/api/datasources)" == 401 ]] || fail "Grafana API answers without login"
[[ "$(code -u admin:prom-operator http://127.0.0.1:13000/api/datasources)" == 401 ]] ||
  fail "Grafana accepts the chart's default password"
grafana() { curl -s -K <(printf 'user = "admin:%s"\n' "$(cat "$password_file")") "http://127.0.0.1:13000$1"; }
sources="$(grafana /api/datasources | json "','.join(sorted(s['uid'] for s in d))")"
[[ "$sources" == "loki,prometheus,tempo" ]] || fail "Grafana data sources: $sources"
boards="$(grafana '/api/search?type=dash-db' | json "','.join(sorted(b['uid'] for b in d))")"
[[ "$boards" == "vyom-agent,vyom-cluster" ]] || fail "Grafana dashboards: $boards"
pass "Grafana requires the private login; data sources $sources; dashboards $boards"
exposed="$(k get svc -o jsonpath='{range .items[?(@.spec.type!="ClusterIP")]}{.metadata.name} {end}')"
[[ -z "$exposed" && -z "$(k get ingress -o name)" ]] || fail "non-internal exposure: $exposed"
pass "all Services are ClusterIP and there is no Ingress"

# Prometheus: every target healthy, real cluster series present.
prom() { curl -s http://127.0.0.1:19090/api/v1/query --data-urlencode "query=$1" | json "d['data']['result']"; }
down="$(curl -s http://127.0.0.1:19090/api/v1/targets |
  json "' '.join(t['scrapePool'] for t in d['data']['activeTargets'] if t['health'] != 'up')")"
[[ -z "$down" ]] || fail "scrape targets not up: $down"
for query in 'kube_node_status_condition{condition="Ready",status="true"} == 1' \
  'node_memory_MemAvailable_bytes' 'container_memory_working_set_bytes{namespace="kube-system"}' \
  'up{job="alloy"} == 1'; do
  [[ "$(prom "$query")" != "[]" ]] || fail "no series for: $query"
done
[[ "$(prom 'count({__name__=~"kube_(secret|configmap)_.*"})')" == "[]" ]] ||
  fail "Secret or ConfigMap series are being collected"
pass "all scrape targets up; node, kubelet and kube-state-metrics series present; no Secret/ConfigMap series"

# Loki: logs arrive, labels bounded, namespaces allowlisted.
labels="$(curl -s http://127.0.0.1:13100/loki/api/v1/labels | json "','.join(sorted(d.get('data') or []))")"
[[ "$labels" == "container,namespace,service_name,stream" ]] || fail "Loki labels: $labels"
namespaces="$(curl -s http://127.0.0.1:13100/loki/api/v1/label/namespace/values |
  json "','.join(sorted(d.get('data') or []))")"
[[ "$namespaces" =~ ^(observability|observability,vyom)$ ]] || fail "Loki namespaces: $namespaces"
pass "Loki has logs with labels [$labels] from namespaces [$namespaces]"

# Tempo: a synthetic span sent through the backend exporter and Alloy is queryable.
trace_id="$(cd "$root" && OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:14318 \
  uv run --quiet --project backend python backend/scripts/otlp_smoke.py)" || fail "synthetic span was not accepted"
for _ in $(seq 30); do
  [[ "$(code "http://127.0.0.1:13200/api/traces/$trace_id")" == 200 ]] && found=1 && break
  sleep 1
done
[[ "${found:-}" == 1 ]] || fail "trace $trace_id did not reach Tempo within 30s"
pass "synthetic trace $trace_id is queryable in Tempo (pipeline only, not a chat trace)"
