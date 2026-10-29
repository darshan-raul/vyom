#!/usr/bin/env bash
# Live gate for S1.8: the S1 question journey and its telemetry on a Kind install, from a real
# model through the cluster. Run after scripts/vyom-up.sh and scripts/observability-up.sh with
# a model key in place (.local/model-api-key). It spends about a dozen small model requests,
# deliberately breaks things for a few minutes (the model key, the MCP server, Alloy, Tempo, the
# demo `web` replica count) and restores them on exit, even after a failure. Takes about 15 min.
# Telemetry is read through localhost-only port-forwards; Grafana's password stays out of argv.
# Writes working files to .local/s18/ (ignored by Git); prints facts, never a key or token.
#   KUBE_CONTEXT  kubectl context (default: kind-vyom)
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
context="${KUBE_CONTEXT:-kind-vyom}"
[[ "$context" == kind-* ]] || { echo "KUBE_CONTEXT must name a local kind-* context" >&2; exit 1; }
work="$root/.local/s18"
key_file="$root/.local/model-api-key"
password_file="$root/.local/grafana-admin-password"
helper="$root/scripts/s18_gate.py"
k() { kubectl --context "$context" "$@"; }
pass() { echo "PASS  $*"; }
note() { echo "NOTE  $*"; }
fail() { echo "FAIL  $*" >&2; exit 1; }
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
for tool in kubectl curl python3 sha256sum; do command -v "$tool" >/dev/null || fail "missing required tool: $tool"; done
[[ -s "$key_file" && -s "$password_file" ]] || fail "need $key_file and $password_file"
mkdir -p "$work"
rm -f "$work"/*

# ---- plumbing ---------------------------------------------------------------------------
pids=()
forward() { # namespace, service, local port, remote port
  kubectl --context "$context" -n "$1" port-forward "svc/$2" "$3:$4" --address 127.0.0.1 >/dev/null 2>&1 &
  pids+=($!)
  for _ in $(seq 40); do [[ "$(code "http://127.0.0.1:$3/")" != 000 ]] && return 0; sleep 0.5; done
  fail "port-forward to $2 did not answer"
}
restore() {
  set +e
  k -n vyom scale deployment/kubernetes-mcp --replicas=1 >/dev/null 2>&1
  k -n observability scale statefulset/tempo --replicas=1 >/dev/null 2>&1
  k -n observability patch daemonset alloy --type json \
    -p '[{"op":"remove","path":"/spec/template/spec/nodeSelector"}]' >/dev/null 2>&1
  k -n demo scale deployment/web --replicas=1 >/dev/null 2>&1
  k -n vyom create secret generic vyom-model-key --from-file=key="$key_file" --dry-run=client -o yaml |
    k apply -f - >/dev/null 2>&1
  for p in "${pids[@]:-}"; do [[ -n "$p" ]] && kill "$p" 2>/dev/null; done
}
trap restore EXIT

ui=http://127.0.0.1:18080
ask() { # question, outfile -> prints "outcome seconds"
  local seconds
  seconds="$(curl -s -m 90 -w '%{time_total}' -o "$2" "$ui/api/chat" -H 'content-type: application/json' \
    -d "$(python3 -c 'import json,sys; print(json.dumps({"question": sys.argv[1]}))' "$1")")" || true
  echo "$(json "d['outcome']" <"$2" 2>/dev/null || echo none) $seconds"
}
trace_of() { json "d['trace_id']" <"$1"; }
now_ns() { echo "$(date +%s)000000000"; }
loki() { # logql, start_s, end_s, outfile
  curl -s -m 30 http://127.0.0.1:13100/loki/api/v1/query_range --data-urlencode "query=$1" \
    --data-urlencode "start=${2}000000000" --data-urlencode "end=${3}000000000" \
    --data-urlencode limit=5000 --data-urlencode direction=forward >"$4"
}
tempo_forward() { # (re)open the Tempo port-forward; a forward dies when the Tempo pod is replaced
  [[ -n "${tempo_pf:-}" ]] && kill "$tempo_pf" 2>/dev/null
  kubectl --context "$context" -n observability port-forward svc/tempo 13200:3200 --address 127.0.0.1 >/dev/null 2>&1 &
  tempo_pf=$!
  pids+=("$tempo_pf")
  for _ in $(seq 40); do [[ "$(code http://127.0.0.1:13200/ready)" != 000 ]] && return 0; sleep 0.5; done
  return 1
}
tempo() { # trace id, outfile, tries -> 0 if the trace is queryable
  local status
  for _ in $(seq "${3:-30}"); do
    status="$(curl -s -o "$2" -w '%{http_code}' "http://127.0.0.1:13200/api/traces/$1")"
    [[ "$status" == 200 ]] && return 0
    [[ "$status" == 000 ]] && tempo_forward
    sleep 2
  done
  return 1
}
promv() { # query -> first value, or 0 when there is no series
  curl -s -m 20 http://127.0.0.1:19090/api/v1/query --data-urlencode "query=$1" |
    json "(d['data']['result'] or [{'value':[0,'0']}])[0]['value'][1]"
}
atleast() { python3 -c "import sys; sys.exit(0 if float(sys.argv[1]) >= float(sys.argv[2]) else 1)" "$1" "$2"; }
pod_sees() { # sha256 of the model key the API pod has mounted
  k -n vyom exec deploy/vyom-api -- sha256sum /var/run/vyom/model/key 2>/dev/null | cut -d' ' -f1
}
wait_model_key() { # expected sha256
  for _ in $(seq 60); do [[ "$(pod_sees)" == "$1" ]] && return 0; sleep 3; done
  fail "the API pod did not see the new model key within 3 minutes"
}
scrape() { sleep 40; } # Prometheus scrapes every 30 s

k -n vyom rollout status deployment/vyom-api --timeout=60s >/dev/null || fail "Vyom is not installed (run scripts/vyom-up.sh)"
[[ "$(k -n vyom get secret vyom-model-key -o jsonpath='{.data.key}' | wc -c)" -gt 8 ]] || fail "no model key in the cluster"
[[ "$(k auth can-i list pods -n vyom --as system:serviceaccount:observability:alloy)" == yes ]] ||
  fail "Alloy cannot list pods in namespace vyom, so Vyom's logs are not collected (re-run scripts/observability-up.sh)"
forward vyom vyom-ui 18080 8080
forward observability kps-prometheus 19090 9090
forward observability loki 13100 3100
tempo_forward || fail "port-forward to tempo did not answer"
forward observability grafana 13000 80
t0="$(date +%s)"
echo "window start: $(date -u -d "@$t0" +%FT%TZ)  cluster: $context"
echo "pins: $(k -n vyom get deploy -o jsonpath='{range .items[*]}{.spec.template.spec.containers[*].image}{"\n"}{end}' | sort -u | tr '\n' ' ')"

# ---- 1. The question, its evidence, the table and a changed workload ------------------------
pods_seen="$(k -n demo get pods --no-headers -o custom-columns=:metadata.name | tr '\n' ' ')"
read -r outcome seconds <<<"$(ask 'Which pods are unhealthy in the demo namespace? (s18-marker-q1)' "$work/q1.json")"
[[ "$outcome" == answered ]] || fail "q1 outcome $outcome"
tid1="$(trace_of "$work/q1.json")"
json "'broken-' in d['answer']" <"$work/q1.json" | grep -q True || fail "answer does not name the broken pod"
json "set(c['item_id'] for c in d['citations']) <= set(i['id'] for e in d['evidence'] for i in e['items'])" \
  <"$work/q1.json" | grep -q True || fail "a citation does not resolve to collected evidence"
pass "q1 answered in ${seconds}s, names the unhealthy pod, every citation resolves to evidence (trace $tid1)"
baseline="$seconds"

curl -s "$ui/api/kubernetes/pods" >"$work/pods1.json"
mine="$(json "'\n'.join(sorted(i['name'] + ' ' + i['attributes']['status'] for i in d['evidence']['items']))" <"$work/pods1.json")"
[[ "$mine" == "$(k -n demo get pods --no-headers | awk '{print $1, $3}' | sort)" ]] || fail "pods table differs from kubectl"
pass "the direct pods table equals kubectl ($(wc -l <<<"$mine") pods)"

k -n demo scale deployment/web --replicas=2 >/dev/null
k -n demo rollout status deployment/web --timeout=2m >/dev/null
read -r outcome seconds <<<"$(ask 'Which pods are unhealthy in the demo namespace? (s18-marker-q2)' "$work/q2.json")"
[[ "$outcome" == answered ]] || fail "q2 outcome $outcome"
curl -s "$ui/api/kubernetes/pods" >"$work/pods2.json"
names="$(k -n demo get pods --no-headers | awk '{print $1}' | sort)"
[[ "$(json "'\n'.join(sorted(i['name'] for e in d['evidence'] for i in e['items'] if e['source']['path'] == 'mcp'))" <"$work/q2.json")" == "$names" ]] ||
  fail "the agent's evidence missed the changed workload"
[[ "$(json "'\n'.join(sorted(i['name'] for i in d['evidence']['items']))" <"$work/pods2.json")" == "$names" ]] ||
  fail "the pods table missed the changed workload"
[[ "$(json "d['evidence']['collected_at'] > '$(json "d['evidence']['collected_at']" <"$work/pods1.json")'" <"$work/pods2.json")" == True ]] ||
  fail "the second collection is not later"
pass "after scaling web to 2, the agent's evidence and the table both show $(wc -l <<<"$names") pods, from a later collection"
pods_seen="$pods_seen $(tr '\n' ' ' <<<"$names")"
k -n demo scale deployment/web --replicas=1 >/dev/null
tid2="$(trace_of "$work/q2.json")"

# ---- 2. Metrics for the real requests --------------------------------------------------------
scrape
atleast "$(promv 'sum(vyom_chat_requests_total{outcome="answered"})')" 2 || fail "chat answered counter"
atleast "$(promv 'sum(vyom_model_requests_total{outcome="ok"})')" 4 || fail "model ok counter"
atleast "$(promv 'sum(vyom_mcp_client_operations_total{operation="call",outcome="ok"})')" 2 || fail "mcp ok counter"
atleast "$(promv 'sum(vyom_http_requests_total{route="/api/chat",status="200"})')" 2 || fail "http counter"
atleast "$(promv 'sum(vyom_model_tokens_total)')" 1 || fail "token counter"
[[ "$(promv 'count(count by (step) (vyom_graph_step_duration_seconds_count))')" == 3 ]] || fail "graph steps"
atleast "$(promv 'sum(vyom_collector_runs_total{outcome="ok"})')" 1 || fail "collector counter"
pass "Prometheus holds the chat, model, MCP, graph-step, HTTP, token and collector series for the real requests"

# ---- 3. Logs and 4. the trace ----------------------------------------------------------------
loki "{namespace=\"vyom\"} |= \"$tid1\"" "$((t0 - 60))" "$(date +%s)" "$work/loki-q1.json"
summary="$(python3 "$helper" loki-summary "$work/loki-q1.json")"
[[ "$(json "sorted(d['loggers'].items())" <<<"$summary")" == "[('vyom.chat', 1), ('vyom.http', 1), ('vyom.mcp', 1), ('vyom.model', 2)]" && "$(json "d['duplicates']" <<<"$summary")" == 0 ]] ||
  fail "log lines for $tid1: $summary"
pass "Loki holds exactly one http, one chat, two model and one MCP line for trace $tid1, no duplicates"
labels="$(curl -s http://127.0.0.1:13100/loki/api/v1/labels | json "','.join(sorted(d['data']))")"
[[ "$labels" == "container,namespace,service_name,stream" ]] || fail "Loki indexed labels: $labels"
pass "Loki indexes only [$labels]; trace and span IDs are in the line, not labels"
tempo "$tid1" "$work/trace-q1.json" 30 || fail "trace $tid1 is not in Tempo"
tsum="$(python3 "$helper" trace-summary "$work/trace-q1.json")"
json "set(['POST /api/chat','chat.graph','graph.propose','graph.collect','graph.answer','model.client.chat','mcp.client.call','evidence.normalize']) <= set(d['names'])" \
  <<<"$tsum" | grep -q True || fail "trace spans: $tsum"
[[ "$(json "(d['roots'], d['orphans'], d['duplicate_span_ids'])" <<<"$tsum")" == "(1, [], 0)" ]] || fail "trace shape: $tsum"
pass "Tempo holds one connected trace: request, graph (propose, collect, answer), two model calls, MCP call, evidence ($(json "d['spans']" <<<"$tsum") spans, no orphans or duplicates)"

# ---- 5. Log <-> trace navigation as Grafana performs it ---------------------------------------
# Time-limited with one retry: Grafana's SQLite can stall for a while when the host disk is busy.
grafana() {
  curl -s -m 60 --retry 1 --retry-all-errors -K <(printf 'user = "admin:%s"\n' "$(cat "$password_file")") "http://127.0.0.1:13000$1"
}
grafana /api/datasources >"$work/datasources.json"
regex="$(json "[s for s in d if s['type'] == 'loki'][0]['jsonData']['derivedFields'][0]['matcherRegex']" <"$work/datasources.json")"
[[ "$(json "[s for s in d if s['type'] == 'loki'][0]['jsonData']['derivedFields'][0]['datasourceUid']" <"$work/datasources.json")" == tempo ]] ||
  fail "the Loki derived field does not point at Tempo"
[[ "$(python3 "$helper" derived "$work/loki-q1.json" "$regex")" == "$tid1" ]] || fail "derived field does not extract the trace ID"
[[ "$(grafana "/api/datasources/proxy/uid/tempo/api/traces/$tid1" | json "len([s for b in d['batches'] for ss in b['scopeSpans'] for s in ss['spans']])")" == "$(json "d['spans']" <<<"$tsum")" ]] ||
  fail "Grafana's Tempo proxy does not return the trace"
pass "log to trace: the Loki derived field extracts $tid1 from a log line and Grafana's Tempo data source returns that trace"
[[ "$(json "[s for s in d if s['type'] == 'tempo'][0]['jsonData']['tracesToLogsV2']['datasourceUid']" <"$work/datasources.json")" == loki ]] ||
  fail "Tempo's trace-to-logs link does not point at Loki"
n="$(grafana "/api/datasources/proxy/uid/loki/loki/api/v1/query_range?query=%7Bservice_name%3D%22vyom-api%22%7D+%7C%3D+%22$tid1%22&start=$((t0 - 60))000000000&end=$(date +%s)000000000&limit=100" |
  json "sum(len(r['values']) for r in d['data']['result'])")"
[[ "$n" == 5 ]] || fail "trace to logs returned $n lines"
pass "trace to log: Tempo's link target (Loki, by trace ID and service) returns the request's 5 log lines through Grafana"
note "these two links were exercised through Grafana's APIs; clicking them in the Grafana UI is for the owner (Explore > Loki, then the TraceID link; Explore > Tempo, then Logs for this span)"

if [[ "${S18_SKIP:-}" != faults ]]; then  # S18_SKIP=faults runs everything except sections 6-8 (debugging only)
# ---- 6. Provider failure ---------------------------------------------------------------------
before_chat="$(promv 'sum(vyom_chat_requests_total{outcome="model_unavailable"})')"
before_model="$(promv 'sum(vyom_model_requests_total{outcome!="ok"})')"
printf %s invalid-key-for-s18-gate >"$work/bad-key"
k -n vyom create secret generic vyom-model-key --from-file=key="$work/bad-key" --dry-run=client -o yaml | k apply -f - >/dev/null
wait_model_key "$(sha256sum <"$work/bad-key" | cut -d' ' -f1)"
read -r outcome seconds <<<"$(ask 'Which pods are unhealthy in the demo namespace? (s18-marker-model)' "$work/q-model.json")"
[[ "$outcome" == model_unavailable ]] || fail "provider failure outcome $outcome"
json "d['answer'] is None and bool(d['limitation'])" <"$work/q-model.json" | grep -q True || fail "a failed question carried an answer"
tid_model="$(trace_of "$work/q-model.json")"
pass "with a rejected provider key the product says model_unavailable with a fixed limitation and no answer, in ${seconds}s (trace $tid_model)"
k -n vyom create secret generic vyom-model-key --from-file=key="$key_file" --dry-run=client -o yaml | k apply -f - >/dev/null
wait_model_key "$(sha256sum <"$key_file" | cut -d' ' -f1)"
scrape
atleast "$(promv 'sum(vyom_chat_requests_total{outcome="model_unavailable"})')" "$((before_chat + 1))" || fail "chat model_unavailable counter"
atleast "$(promv 'sum(vyom_model_requests_total{outcome!="ok"})')" "$((before_model + 1))" || fail "model error counter"
loki "{namespace=\"vyom\"} |= \"$tid_model\"" "$((t0 - 60))" "$(date +%s)" "$work/loki-model.json"
python3 "$helper" loki-summary "$work/loki-model.json" >/dev/null
grep -q 'model_unavailable' "$work/loki-model.json" || fail "no model_unavailable log line"
tempo "$tid_model" "$work/trace-model.json" 30 || fail "failure trace missing"
json "[a['value']['stringValue'] for b in d['batches'] for ss in b['scopeSpans'] for s in ss['spans'] if s['name'] == 'chat.graph' for a in s['attributes'] if a['key'] == 'vyom.outcome']" \
  <"$work/trace-model.json" | grep -q model_unavailable || fail "span outcome"
pass "the provider failure is visible as a chat counter, a model error counter, a log line and a span outcome"
read -r outcome seconds <<<"$(ask 'Which pods are unhealthy in the demo namespace? (s18-marker-restored)' "$work/q-restored.json")"
[[ "$outcome" == answered ]] || fail "after restoring the key: $outcome"
pass "with the key restored the same question is answered"

# ---- 7. MCP failure --------------------------------------------------------------------------
before_chat="$(promv 'sum(vyom_chat_requests_total{outcome="no_evidence"})')"
before_mcp="$(promv 'sum(vyom_mcp_client_operations_total{outcome!="ok"})')"
k -n vyom scale deployment/kubernetes-mcp --replicas=0 >/dev/null
k -n vyom wait --for=delete pod -l app.kubernetes.io/name=kubernetes-mcp --timeout=90s >/dev/null
read -r outcome seconds <<<"$(ask 'Which pods are unhealthy in the demo namespace? (s18-marker-mcp)' "$work/q-mcp.json")"
[[ "$outcome" == no_evidence ]] || fail "MCP failure outcome $outcome"
tid_mcp="$(trace_of "$work/q-mcp.json")"
curl -s "$ui/api/kubernetes/pods" >"$work/pods-mcp-down.json"
[[ "$(json "d['evidence']['state']" <"$work/pods-mcp-down.json")" == complete ]] || fail "pods table not complete with MCP down"
pass "with the MCP server down chat says no_evidence in ${seconds}s (trace $tid_mcp) while the direct pods table stays complete"
k -n vyom scale deployment/kubernetes-mcp --replicas=1 >/dev/null
k -n vyom rollout status deployment/kubernetes-mcp --timeout=3m >/dev/null
scrape
atleast "$(promv 'sum(vyom_chat_requests_total{outcome="no_evidence"})')" "$((before_chat + 1))" || fail "no_evidence counter"
atleast "$(promv 'sum(vyom_mcp_client_operations_total{outcome!="ok"})')" "$((before_mcp + 1))" || fail "mcp error counter"
loki "{namespace=\"vyom\"} |= \"$tid_mcp\"" "$((t0 - 60))" "$(date +%s)" "$work/loki-mcp.json"
grep -q 'no_evidence' "$work/loki-mcp.json" || fail "no no_evidence log line"
tempo "$tid_mcp" "$work/trace-mcp.json" 30 || fail "MCP failure trace missing"
pass "the MCP failure is visible as a chat counter, an MCP error counter, a log line and a trace"
read -r outcome seconds <<<"$(ask 'Which pods are unhealthy in the demo namespace? (s18-marker-mcp-restored)' "$work/q-mcp2.json")"
[[ "$outcome" == answered ]] || fail "after restoring MCP: $outcome"
pass "with the MCP server back the question is answered"

# ---- 8. Telemetry interruption, separately ----------------------------------------------------
# 8a. The collector (Alloy) stops.
k -n observability patch daemonset alloy -p '{"spec":{"template":{"spec":{"nodeSelector":{"vyom.dev/s18-pause":"true"}}}}}' >/dev/null
for _ in $(seq 30); do [[ "$(k -n observability get ds alloy -o jsonpath='{.status.numberReady}')" == 0 ]] && break; sleep 2; done
[[ "$(k -n observability get ds alloy -o jsonpath='{.status.numberReady}')" == 0 ]] || fail "alloy did not stop"
read -r outcome seconds <<<"$(ask 'Which pods are unhealthy in the demo namespace? (s18-marker-alloy-down)' "$work/q-alloy.json")"
[[ "$outcome" == answered ]] || fail "chat with the collector down: $outcome"
python3 -c "import sys; sys.exit(0 if float(sys.argv[1]) < max(30, 4*float(sys.argv[2])) else 1)" "$seconds" "$baseline" ||
  fail "chat slowed to ${seconds}s with the collector down (baseline ${baseline}s)"
tid_alloy="$(trace_of "$work/q-alloy.json")"
pass "with Alloy stopped the question is still answered in ${seconds}s (baseline ${baseline}s)"
for _ in $(seq 30); do
  [[ "$(promv 'kube_daemonset_status_number_ready{daemonset="alloy"}')" == 0 ]] && break
  sleep 5
done
[[ "$(promv 'kube_daemonset_status_number_ready{daemonset="alloy"}')" == 0 ]] || fail "the collector outage is not visible in Prometheus"
pass "the collector outage is independently visible: kube_daemonset_status_number_ready{daemonset=\"alloy\"} = 0, DaemonSet not ready"
k -n observability patch daemonset alloy --type json -p '[{"op":"remove","path":"/spec/template/spec/nodeSelector"}]' >/dev/null
k -n observability rollout status daemonset/alloy --timeout=3m >/dev/null
for _ in $(seq 40); do
  loki "{namespace=\"vyom\"} |= \"$tid_alloy\"" "$((t0 - 60))" "$(date +%s)" "$work/loki-alloy.json"
  [[ "$(json "sum(len(r['values']) for r in d['data']['result'])" <"$work/loki-alloy.json")" -ge 5 ]] && break
  sleep 5
done
[[ "$(json "sum(len(r['values']) for r in d['data']['result'])" <"$work/loki-alloy.json")" -ge 5 ]] ||
  fail "log lines written during the outage did not arrive after recovery"
pass "after recovery Loki has the 5 log lines written while Alloy was down (log files were read from the saved position: no log loss)"
if tempo "$tid_alloy" "$work/trace-alloy.json" 10; then
  note "the trace from the outage ($tid_alloy) reached Tempo anyway (the exporter retried or Alloy was back in time)"
else
  note "the trace from the outage ($tid_alloy) is not in Tempo: its spans were dropped, as designed (bounded queue, no replay)"
fi
read -r outcome seconds <<<"$(ask 'Which pods are unhealthy in the demo namespace? (s18-marker-alloy-back)' "$work/q-alloy2.json")"
tid_alloy2="$(trace_of "$work/q-alloy2.json")"
tempo "$tid_alloy2" "$work/trace-alloy2.json" 30 || fail "after recovery a new trace did not reach Tempo"
pass "after Alloy recovered, a new question's trace $tid_alloy2 reached Tempo"

# 8b. The trace store (Tempo) stops.
# Per current Alloy pod: after a restart Prometheus still returns the old pod's series for 5 minutes.
alloy_pod="$(k -n observability get pods -l app.kubernetes.io/name=alloy -o jsonpath='{.items[0].metadata.name}')"
failed_spans() { promv "sum(otelcol_exporter_send_failed_spans_total{pod=\"$alloy_pod\"})"; }
before_failed="$(failed_spans)"
k -n observability scale statefulset/tempo --replicas=0 >/dev/null
k -n observability wait --for=delete pod/tempo-0 --timeout=2m >/dev/null
read -r outcome seconds <<<"$(ask 'Which pods are unhealthy in the demo namespace? (s18-marker-tempo-down)' "$work/q-tempo.json")"
[[ "$outcome" == answered ]] || fail "chat with Tempo down: $outcome"
tid_tempo="$(trace_of "$work/q-tempo.json")"
pass "with Tempo stopped the question is still answered in ${seconds}s"
for _ in $(seq 36); do
  atleast "$(failed_spans)" "$((before_failed + 1))" && break
  sleep 5
done
atleast "$(failed_spans)" "$((before_failed + 1))" ||
  fail "dropped spans are not visible in otelcol_exporter_send_failed_spans_total"
pass "the lost spans are counted: otelcol_exporter_send_failed_spans_total rose by $(python3 -c "print(int(float('$(failed_spans)') - float('$before_failed')))")"
k -n observability scale statefulset/tempo --replicas=1 >/dev/null
k -n observability rollout status statefulset/tempo --timeout=3m >/dev/null
# After an outage Alloy's gRPC connection to Tempo backs off. Ask a fresh question every minute
# and measure when the first one becomes queryable (limit 15 minutes).
tempo_forward || fail "port-forward to tempo did not answer after its restart"
recovered="$(date +%s)"
asked_ids=()
arrived=""
last_ask=0
while (( $(date +%s) - recovered < 900 )); do
  if (( $(date +%s) - last_ask >= 60 )); then
    ask 'Which pods are unhealthy in the demo namespace? (s18-marker-tempo-back)' "$work/q-tempo2.json" >/dev/null
    asked_ids+=("$(trace_of "$work/q-tempo2.json")")
    last_ask="$(date +%s)"
  fi
  for id in "${asked_ids[@]}"; do
    if tempo "$id" "$work/trace-tempo2.json" 1; then arrived="$id"; break 2; fi
  done
  sleep 10
done
[[ -n "$arrived" ]] || fail "no trace was queryable within 15 minutes of Tempo's recovery"
delay=$(($(date +%s) - recovered))
pass "after Tempo recovered, a new trace ($arrived) became queryable by ID $delay s after Tempo was ready (${#asked_ids[@]} question(s) asked meanwhile; the app was never slowed)"
if tempo "$tid_tempo" "$work/trace-tempo.json" 3; then note "the trace from the Tempo outage ($tid_tempo) arrived after recovery"; else note "the trace from the Tempo outage ($tid_tempo) is lost, as designed"; fi

fi

# ---- 9. Stored signals: prohibited content and duplicates -------------------------------------
t1="$(date +%s)"
loki '{namespace="vyom"}' "$((t0 - 60))" "$t1" "$work/loki-all.json"
python3 "$helper" dump-summary "$work/loki-all.json" >"$work/dump-summary.txt" || fail "duplicate log records: $(cat "$work/dump-summary.txt")"
pass "Loki, namespace vyom, $(cat "$work/dump-summary.txt"): no exact duplicate lines, no repeated (trace, span, logger) record, including across an Alloy restart when the fault sections ran"
curl -s -m 30 "http://127.0.0.1:13200/api/search" --get --data-urlencode "tags=service.name=vyom-api" \
  --data-urlencode "start=$((t0 - 60))" --data-urlencode "end=$t1" --data-urlencode limit=200 >"$work/search.json"
ids="$(json "' '.join(t['traceID'] for t in d['traces'])" <"$work/search.json")"
i=0; for id in $ids; do tempo "$id" "$work/all-trace-$i.json" 3 && i=$((i + 1)); done
dupspans=0
for f in "$work"/all-trace-*.json; do
  [[ "$(python3 "$helper" trace-summary "$f" | json "d['duplicate_span_ids']")" == 0 ]] || dupspans=1
done
[[ $dupspans == 0 ]] || fail "duplicate span IDs inside a trace"
pass "Tempo: $i vyom-api traces in the window, no duplicate span IDs inside any"
curl -s "http://127.0.0.1:19090/api/v1/series" --get --data-urlencode 'match[]={__name__=~"vyom_.*"}' \
  --data-urlencode "start=$((t0 - 60))" --data-urlencode "end=$t1" >"$work/series.json"
extra="$(json "sorted(set(k for s in d['data'] for k in s) - {'__name__','container','endpoint','instance','job','namespace','pod','service','method','route','status','server','tool','operation','outcome','provider','model','direction','step','le','collector'})" <"$work/series.json")"
[[ "$extra" == "[]" ]] || fail "unexpected metric labels: $extra"
pass "Prometheus: $(json "len(d['data'])" <"$work/series.json") vyom_ series, labels limited to the bounded set"
# shellcheck disable=SC2086
if python3 "$helper" scan "$key_file" s18-marker "Bearer " "sk-or-" eyJ vyom-demo-literal-env-value $pods_seen \
  "$(json "d['evidence'][0]['items'][0]['id']" <"$work/q1.json")" -- \
  "$work/loki-all.json" "$work"/all-trace-*.json "$work/series.json" >"$work/scan.txt"; then
  pass "no question text, credential, key, token, literal env value, pod name or resource ID in $(json "d['files']" <"$work/scan.txt") stored artifacts (all Loki lines in vyom, $i traces, all vyom_ series)"
else
  fail "prohibited content in telemetry: $(cat "$work/scan.txt")"
fi

# ---- 10. Capacity facts for the re-estimate -----------------------------------------------------
gib() { python3 -c "print(round(float('$1')/2**30, 2))"; }
echo "capacity: peak memory working set (last hour) vyom $(gib "$(promv 'sum(max_over_time(container_memory_working_set_bytes{namespace="vyom",container!=""}[1h]))')") GiB, observability $(gib "$(promv 'sum(max_over_time(container_memory_working_set_bytes{namespace="observability",container!=""}[1h]))')") GiB; node memory $(gib "$(promv 'sum(node_memory_MemTotal_bytes)')") GiB total, $(gib "$(promv 'sum(node_memory_MemAvailable_bytes)')") GiB available"
echo "capacity: requested cpu $(promv 'sum(kube_pod_container_resource_requests{resource="cpu"})') cores of $(promv 'sum(kube_node_status_allocatable{resource="cpu"})')"
node="$(k get nodes -o jsonpath='{.items[0].metadata.name}')"
# Kind keeps PersistentVolumes on the node's disk; the store images have no du.
echo "capacity: stored data on the node: $(docker exec "$node" sh -c 'du -sh /var/local-path-provisioner/* 2>/dev/null' 2>/dev/null | sed -E 's|/var/local-path-provisioner/pvc-[0-9a-f-]+_[^_]*_||' | tr '\t\n' ' ' || echo n/a)"
echo "window end: $(date -u -d "@$t1" +%FT%TZ)"
echo "S1.8 gate checks passed"
