#!/usr/bin/env bash
# Application gate (R1): the installed Vyom release on Kind. Read-only apart from triggering the
# collector-token refresher once. Needs scripts/vyom-up.sh to have run. Opens localhost-only
# port-forwards for its duration. Every line is a PASS or the script stops with FAIL.
#   KUBE_CONTEXT  kubectl context (default: kind-vyom)
# Checks marked [image] run the built image with Docker, not the cluster.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
context="${KUBE_CONTEXT:-kind-vyom}"
[[ "$context" == kind-* ]] || { echo "KUBE_CONTEXT must name a local kind-* context" >&2; exit 1; }
k() { kubectl --context "$context" "$@"; }
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*" >&2; exit 1; }
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
can() { # service account, verb, resource [namespace]: yes/no
  k auth can-i "$2" "$3" ${4:+-n "$4"} --as "system:serviceaccount:vyom:$1" 2>/dev/null || true
}

pids=()
trap 'for p in "${pids[@]:-}"; do [[ -n "$p" ]] && kill "$p" 2>/dev/null || true; done' EXIT
forward() { # namespace, service, local port, remote port
  kubectl --context "$context" -n "$1" port-forward "svc/$2" "$3:$4" --address 127.0.0.1 \
    >/dev/null 2>&1 &
  pids+=($!)
  for _ in $(seq 40); do
    [[ "$(code "http://127.0.0.1:$3/")" != 000 ]] && return 0
    sleep 0.5
  done
  fail "port-forward to $2 did not answer"
}

for tool in kubectl helm curl python3 docker; do
  command -v "$tool" >/dev/null || fail "missing required tool: $tool"
done

# -- The release and its workloads ----------------------------------------------------------
status="$(helm --kube-context "$context" -n vyom status vyom -o json | json "d['info']['status']")"
[[ "$status" == deployed ]] || fail "release status is $status"
pass "release vyom is deployed"
for deployment in vyom-api vyom-ui kubernetes-mcp; do
  k -n vyom rollout status "deployment/$deployment" --timeout=60s >/dev/null ||
    fail "$deployment is not available"
done
pass "vyom-api, vyom-ui and kubernetes-mcp are available"
[[ "$(k -n vyom get cronjob vyom-collector-token-refresh -o jsonpath='{.spec.schedule}')" == "*/30 * * * *" ]] ||
  fail "token refresher schedule"
pass "collector token refresher is scheduled every 30 minutes"

# -- Pod hardening and exposure -------------------------------------------------------------
bad="$(k -n vyom get pods,cronjobs -o json | json "
'\n'.join(
  f\"{i['metadata']['name']}/{c['name']}\"
  for i in d['items']
  for s in [i['spec'].get('jobTemplate', {}).get('spec', {}).get('template', {}).get('spec', i['spec'])]
  for c in s['containers']
  if not (c.get('securityContext', {}).get('readOnlyRootFilesystem')
          and c['securityContext'].get('allowPrivilegeEscalation') is False
          and c['securityContext'].get('capabilities', {}).get('drop') == ['ALL']
          and s.get('securityContext', {}).get('runAsNonRoot'))
)")"
[[ -z "$bad" ]] || fail "containers without the restricted security context: $bad"
pass "every container is non-root, read-only, no privilege escalation, all capabilities dropped"
types="$(k get svc -A -l app.kubernetes.io/part-of=vyom -o jsonpath='{range .items[*]}{.spec.type}{"\n"}{end}' | sort -u)"
[[ "$types" == ClusterIP ]] || fail "Vyom services are not all ClusterIP: $types"
[[ -z "$(k get ingress -A -o name 2>/dev/null)" ]] || fail "an Ingress exists"
pass "every Vyom Service is ClusterIP and there is no Ingress"

# -- Identities -----------------------------------------------------------------------------
[[ "$(can vyom-api list pods demo)" == no ]] || fail "vyom-api can list pods in demo"
[[ "$(can vyom-api get secrets vyom)" == no ]] || fail "vyom-api can read Secrets"
# The endpoint permission is a name only (no such API type), so ask the way the proxy does.
sar() { # service account: allowed true/false for the endpoint
  k create -o jsonpath='{.status.allowed}' -f - <<JSON
{"apiVersion":"authorization.k8s.io/v1","kind":"SubjectAccessReview","spec":{
 "user":"system:serviceaccount:vyom:$1","resourceAttributes":{"group":"vyom.dev",
 "resource":"mcpendpoints","namespace":"vyom","name":"kubernetes","verb":"create"}}}
JSON
}
[[ "$(sar vyom-api)" == true ]] || fail "vyom-api cannot use the MCP endpoint"
[[ "$(sar vyom-collector)" != true ]] || fail "vyom-collector can use the MCP endpoint"
pass "vyom-api may use the MCP endpoint and has no Kubernetes read access"
[[ "$(can vyom-collector list pods demo)" == yes ]] || fail "vyom-collector cannot list demo pods"
for denied in "get pods demo" "list pods vyom" "list secrets demo" "create pods/exec demo" "list nodes"; do
  # shellcheck disable=SC2086
  [[ "$(can vyom-collector $denied)" == no ]] || fail "vyom-collector may: $denied"
done
pass "vyom-collector may list pods in demo and is denied get, other namespaces, Secrets, exec and nodes"
[[ "$(can kubernetes-mcp list pods demo)" == yes ]] || fail "kubernetes-mcp cannot list demo pods"
[[ "$(can kubernetes-mcp delete pods demo)" == no && "$(can kubernetes-mcp list secrets demo)" == no ]] ||
  fail "kubernetes-mcp has more than a pod list"
pass "kubernetes-mcp may list pods in demo and nothing more"
as_refresher="--as system:serviceaccount:vyom:vyom-token-refresher"
# shellcheck disable=SC2086
[[ "$(k auth can-i create serviceaccounts/vyom-collector --subresource=token -n vyom $as_refresher 2>/dev/null || true)" == yes ]] ||
  fail "refresher cannot mint collector tokens"
# shellcheck disable=SC2086
[[ "$(k auth can-i create serviceaccounts/vyom-api --subresource=token -n vyom $as_refresher 2>/dev/null || true)" == no ]] ||
  fail "refresher can mint tokens for vyom-api"
for denied in "get secrets vyom" "list secrets vyom" "delete secrets vyom" "list pods demo" "create pods vyom"; do
  # shellcheck disable=SC2086
  [[ "$(can vyom-token-refresher $denied)" == no ]] || fail "token refresher may: $denied"
done
pass "token refresher may mint collector tokens and patch a Secret, and read, list or delete nothing"
# resourceNames: it may only patch the one Secret.
[[ "$(k auth can-i patch secret/vyom-collector-token -n vyom --as system:serviceaccount:vyom:vyom-token-refresher 2>/dev/null || true)" == yes ]] ||
  fail "refresher cannot patch its Secret"
[[ "$(k auth can-i patch secret/vyom-model-key -n vyom --as system:serviceaccount:vyom:vyom-token-refresher 2>/dev/null || true)" == no ]] ||
  fail "refresher can patch another Secret"
pass "the refresher may patch only its one Secret"

# -- Credentials stay private ---------------------------------------------------------------
release="$(helm --kube-context "$context" -n vyom get all vyom)"
for needle in "BEGIN PRIVATE KEY" "sk-or-" "eyJhbGci"; do
  grep -q "$needle" <<<"$release" && fail "release contents contain $needle"
done
[[ "$(k -n vyom get configmap vyom-operator -o json | json "d['data']['operator.json'].count('\"credential_ref\": \"file:/var/run/vyom/')")" == 3 ]] ||
  fail "operator file does not reference mounted files"
pass "the release and the operator file hold credential references only: no key, token or certificate"
env_dump="$(k -n vyom get deployment vyom-api -o json | json "[e['name'] for e in d['spec']['template']['spec']['containers'][0]['env']]")"
[[ "$env_dump" != *KEY* && "$env_dump" != *TOKEN* ]] || fail "credential-like environment variable: $env_dump"
pass "the API pod has no credential in its environment"

# -- The collector's token (K8S02) ----------------------------------------------------------
read_token() { k -n vyom get secret vyom-collector-token -o jsonpath='{.data.token}' | base64 -d; }
lifetime() { python3 -c "
import base64, json, sys
p = sys.stdin.read().strip().split('.')[1]
c = json.loads(base64.urlsafe_b64decode(p + '=' * (-len(p) % 4)))
print(c['exp'] - c['iat'], c['sub'])"; }
first="$(read_token)"
[[ -n "$first" ]] || fail "collector token Secret is empty"
read -r seconds subject <<<"$(lifetime <<<"$first")"
[[ "$subject" == system:serviceaccount:vyom:vyom-collector ]] || fail "token subject is $subject"
((seconds <= 3600)) || fail "token lifetime is $seconds s"
pass "the collector token is for vyom-collector and lives $seconds s"
k -n vyom delete job vyom-collector-token-check --ignore-not-found >/dev/null
sleep 1.1  # token issue times have one-second resolution
k -n vyom create job vyom-collector-token-check --from=cronjob/vyom-collector-token-refresh >/dev/null
k -n vyom wait --for=condition=complete job/vyom-collector-token-check --timeout=120s >/dev/null ||
  fail "the refresher job did not complete"
k -n vyom delete job vyom-collector-token-check >/dev/null
[[ "$(read_token)" != "$first" ]] || fail "the refresher did not replace the token"
pass "the refresher job replaces the token"

# -- The application ------------------------------------------------------------------------
forward vyom vyom-ui 18080 8080
forward vyom vyom-api 18000 8000
[[ "$(code http://127.0.0.1:18080/)" == 200 ]] || fail "UI does not answer"
[[ "$(code http://127.0.0.1:18080/kubernetes)" == 200 ]] || fail "UI route /kubernetes does not answer"
[[ "$(curl -s http://127.0.0.1:18080/api/health | json "d['status']")" == ok ]] || fail "UI cannot reach the API"
pass "the UI serves its routes and forwards /api to the API"
agent="$(curl -s http://127.0.0.1:18000/api/agent)"
[[ "$(json "d['scope']" <<<"$agent")" == "{'connection_id': 'kind-vyom', 'namespace': 'demo'}" ]] ||
  fail "agent scope: $agent"
[[ "$(json "[t['id'] for t in d['tools']]" <<<"$agent")" == "['kubernetes__pods_list_in_namespace']" ]] ||
  fail "agent tools: $agent"
pass "GET /api/agent reports scope demo and the one MCP tool"

view="$(curl -s http://127.0.0.1:18000/api/kubernetes/pods)"
[[ "$(json "d['evidence']['state']" <<<"$view")" == complete ]] || fail "pods view: $(json "d['evidence']['state'], d['evidence']['errors']" <<<"$view")"
mine="$(json "'\n'.join(sorted(i['name'] + ' ' + i['attributes']['status'] for i in d['evidence']['items']))" <<<"$view")"
theirs="$(k -n demo get pods --no-headers | awk '{print $1, $3}' | sort)"
[[ "$mine" == "$theirs" ]] || fail "pods view differs from kubectl:\n$mine\n--\n$theirs"
[[ "$(json "d['evidence']['source']['path']" <<<"$view")" == direct ]] || fail "pods view path"
pass "the direct pod view in the cluster equals kubectl -n demo get pods ($(wc -l <<<"$theirs") pods)"

# -- The in-cluster MCP path (first exercised here) -----------------------------------------
probe="$(k -n vyom exec -i deploy/vyom-api -- python - <"$root/scripts/incluster_probe.py")" ||
  fail "the in-cluster probe failed"
[[ "$(json "d['discovery_error']" <<<"$probe")" == None ]] || fail "MCP discovery: $probe"
[[ "$(json "d['state'], d['path'], d['errors']" <<<"$probe")" == "complete mcp []" ]] || fail "MCP call: $probe"
[[ "$(json "d['upstream']" <<<"$probe")" == *kubernetes* ]] || fail "unexpected upstream: $probe"
mcp_pods="$(json "'\n'.join(d['pods'])" <<<"$probe")"
[[ "$mcp_pods" == "$(k -n demo get pods --no-headers | awk '{print "demo/" $1}' | sort)" ]] ||
  fail "MCP pods differ from kubectl: $mcp_pods"
pass "from inside the API pod: projected token accepted, endpoint certificate trusted, tool discovered and called, pods equal kubectl"
# A caller without the audience-bound token is refused by the proxy (unauthenticated).
anon="$(k -n vyom exec deploy/vyom-api -- python -c "
import ssl, urllib.request, urllib.error
ctx = ssl.create_default_context(cafile='/etc/vyom/mcp-ca/tls.crt')
try:
    urllib.request.urlopen('https://kubernetes-mcp.vyom.svc:8443/mcp', context=ctx)
except urllib.error.HTTPError as e:
    print(e.code)")"
[[ "$anon" == 401 ]] || fail "unauthenticated MCP call answered $anon"
pass "an unauthenticated call to the MCP endpoint from the API pod is refused (401)"

# -- Production mode ------------------------------------------------------------------------
api_image="$(k -n vyom get deployment vyom-api -o jsonpath='{.spec.template.spec.containers[0].image}')"
for mode in production unset; do
  env_args=()
  [[ "$mode" == unset ]] || env_args=(-e "VYOM_MODE=$mode")
  if out="$(docker run --rm "${env_args[@]}" "$api_image" python -c 'import vyom.api.app' 2>&1)"; then
    fail "[image] VYOM_MODE=$mode started the API"
  fi
  grep -q DevelopmentIdentityRefused <<<"$out" || fail "[image] VYOM_MODE=$mode failed for another reason"
done
pass "[image] production mode, and no mode at all, refuse to start with the development identity"

# -- Observability --------------------------------------------------------------------------
# Read the installed setting so disabled metrics are explicit, never a false pass.
monitor="$(helm --kube-context "$context" -n vyom get values vyom -a -o json | json "d['serviceMonitor']['enabled']")"
if [[ "$monitor" == True ]]; then
forward observability kps-prometheus 19090 9090
# A fresh ServiceMonitor may arrive after Prometheus starts. Allow its projected
# configuration and the reloader's watch interval to settle before the first scrape.
# The pinned reloader took three minutes to reload during the fresh metrics gate.
for _ in $(seq 100); do
  up="$(curl -s --get http://127.0.0.1:19090/api/v1/query --data-urlencode 'query=up{namespace="vyom",service="vyom-api"}' |
    json "[r['value'][1] for r in d['data']['result']]")"
  [[ "$up" == "['1']" ]] && break
  sleep 3
done
[[ "$up" == "['1']" ]] || fail "Prometheus does not scrape vyom-api (up=$up)"
pass "Prometheus scrapes the API (up{service=\"vyom-api\"} = 1)"
else
  echo "SKIP  Prometheus scrape (ServiceMonitor disabled in installed release)"
fi
echo "Application checks passed (optional telemetry reported separately)"
