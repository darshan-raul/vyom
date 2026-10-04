# Vyom Kind chat POC

A separate, small experiment outside the six-sprint delivery plan. Run a React/TypeScript/Vite + shadcn/ui frontend and FastAPI backend in **Kind cluster `app`**, then ask questions about pods and deployments in one namespace in **Kind cluster `target`**. No RAG, MCP, LangGraph, databases, observability stack or persistent history. This does not close any Vyom sprint gate.

The backend collects a fresh read-only snapshot through the target Kubernetes REST API, projects allowed status fields, and uses LangChain’s `ChatPromptTemplate` + `ChatOpenAI` to send that evidence to a configured OpenAI-compatible Chat Completions endpoint. The browser shows the answer, resource details, collection time and complete/partial/unavailable coverage. The last four browser messages can accompany a question for follow-up context; fresh evidence supplies facts. Clearing/reloading the page loses conversation history.

## Layout

```text
Browser → localhost port-forward → UI/nginx in app cluster → API in app cluster
                                                          ├─ target API: list pods/deployments
                                                          └─ compatible model endpoint
```

- `backend/`: application, requirements, Dockerfile and offline fixture tests.
- `frontend/`: shadcn Button/Textarea source, chat/evidence UI, Dockerfile and nginx proxy.
- `charts/app/`: private UI/API Deployments and ClusterIP Services. References your existing credential Secrets.
- `charts/target-access/`: ServiceAccount + namespace Role/RoleBinding in the target cluster; optional demo workload.
- `values.example.yaml`: nonsecret configuration to copy into ignored `values.local.yaml`.

Only code checks were run by the agent. **You run every Docker, Kind, kubectl and Helm step below.** No cluster installation, chart lint/render, image build, network check or live model call has been performed. These are setup instructions, not a record of successful deployment.

## Code checks only

Use Python 3.12+ and Node 22.12+ with npm:

```sh
cd poc/kind-chat/backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
cd ../frontend
npm ci
npm run typecheck
npm run build
```

Tests use HTTPX MockTransport and ASGI application code; they do not contact Kubernetes or a model. The frontend build only compiles application assets. Source dependencies are pinned and frontend installs use the committed npm lockfile.

## 1. Create your two local clusters

From `poc/kind-chat/`, with Docker running and `kind`, `kubectl`, and `helm` installed:

```sh
kind create cluster --name app
kind create cluster --name target
```

Default Docker-provider Kind clusters share Docker's `kind` network. The backend will use the **target control-plane's internal Docker IP on port 6443**. Do not use `https://127.0.0.1:<host-port>` from a pod: that points to the pod's own loopback. If you use a different Docker network/provider, supply a target API address reachable from the app cluster's pods and covered by its TLS certificate. TLS verification stays enabled; this POC has no insecure-skip option.

## 2. Install target permissions with Helm

```sh
helm upgrade --install vyom-reader ./charts/target-access \
  --kube-context kind-target --namespace demo --create-namespace \
  --set demo.enabled=true
```

Omit `--set demo.enabled=true` if you already have pods/deployments to inspect. The chart grants **list pods and list deployments in `demo` only**. No Secret/log/exec reads, writes or cluster-wide grants. The backend has no configurable arbitrary API path, command execution or mutation endpoint.

## 3. Prepare private credentials and target address

```sh
umask 077
mkdir -p .private
kubectl --context kind-target --namespace demo create token vyom-poc-reader \
  --duration=1h > .private/target-token
kubectl config view --context kind-target --minify --raw \
  -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' \
  | base64 --decode > .private/target-ca.crt
docker inspect --format '{{(index .NetworkSettings.Networks "kind").IPAddress}}' \
  target-control-plane
```

Use the printed internal IP in `target.server`, e.g. `https://<printed-IP>:6443`. CA/token files stay under ignored `.private/`; do not use an admin kubeconfig or turn off TLS verification. The API server chooses the actual token lifetime; the requested one hour is not a perpetual credential.

Put your compatible model key into `.private/api-key` with an editor or your preferred private mechanism. No key belongs in Helm values, image build arguments, source files or browser configuration. The application strips surrounding key whitespace on startup.

## 4. Create the app-cluster Secrets

Create the app namespace and two Secrets from those private files:

```sh
kubectl --context kind-app create namespace vyom-poc --dry-run=client -o yaml \
  | kubectl --context kind-app apply -f -
kubectl --context kind-app --namespace vyom-poc create secret generic vyom-poc-model \
  --from-file=api-key=.private/api-key --dry-run=client -o yaml \
  | kubectl --context kind-app apply -f -
kubectl --context kind-app --namespace vyom-poc create secret generic vyom-poc-target \
  --from-file=token=.private/target-token --from-file=ca.crt=.private/target-ca.crt \
  --dry-run=client -o yaml | kubectl --context kind-app apply -f -
```

The model key is injected into the backend with `secretKeyRef`. Target token/CA are mounted read-only; the token is reread on every question. Both workloads disable the app cluster's automatic ServiceAccount token mount; the POC never falls back to app-cluster credentials.

## 5. Build and load your images

```sh
docker build -t vyom-kind-chat-api:0.1.0 ./backend
docker build -t vyom-kind-chat-ui:0.1.0 ./frontend
kind load docker-image vyom-kind-chat-api:0.1.0 --name app
kind load docker-image vyom-kind-chat-ui:0.1.0 --name app
```

The API image uses Python 3.12. The UI builds with Node 22 and serves from unprivileged nginx. The chart sets resource limits, nonroot users, read-only root filesystems and probes; nginx gets small writable volumes for generated config and temporary files. No image/Helm checks were run by the agent.

## 6. Configure and install the app with Helm

```sh
cp values.example.yaml values.local.yaml
```

Edit the ignored `values.local.yaml`: set `target.server` to the target internal API address, `model.baseUrl` to your compatible **API base including `/v1` where required**, and `model.name` to its supported model ID. LangChain’s OpenAI integration calls `/chat/completions` with `max_completion_tokens=1200`; your endpoint must support this standard parameter. If your model server runs locally, its address must also be reachable from the API pod; `localhost` in that pod does not mean your workstation. The default endpoint in the example is only a convenience and is not automatic fallback.

The target namespace must match the namespace where the target-access release grants permissions. If you change image tags, change the chart values and load matching images into `app`.

```sh
helm upgrade --install vyom-poc ./charts/app \
  --kube-context kind-app --namespace vyom-poc --create-namespace \
  --values values.local.yaml
kubectl --context kind-app --namespace vyom-poc port-forward --address 127.0.0.1 \
  service/vyom-poc-frontend 8080:80
```

Open **http://127.0.0.1:8080**. Questions to try: “Which pods are unhealthy?”, “Summarize deployment readiness”, “Which pods have restarted?” Model output is displayed as plain text. All resource text is evidence, not instructions; the model cannot choose API paths, credentials or namespace authority.

`/api/health` proves the backend started with configuration; it does **not** prove target/model connectivity. A question performs those actual calls. Complete empty lists mean zero observed resources; denial, timeout, missing credentials and partial collection are shown separately. Provider failure retains evidence and reports unavailable rather than generating a fallback answer.

LangSmith tracing is explicitly disabled, including when tracing environment variables are set. Inference uses one asynchronous LangChain call with no retries or model cache.

## Refresh an expired target token

When questions show `unauthorized`, generate a fresh token in `target`, update `vyom-poc-target` in `app` using the step-4 command, and wait for the projected Secret volume to refresh. The backend rereads the token without restart. If you rotate the **model key**, update its Secret and restart the API Deployment because environment variables do not refresh automatically:

```sh
kubectl --context kind-app --namespace vyom-poc rollout restart deployment/vyom-poc-api
```

Browser “Stop waiting” aborts the browser request, not a Kubernetes/model operation. The backend independently limits a question to 60 seconds, two concurrent requests, two pages of 25 resources per kind, decoded upstream responses to 512 KB, model evidence context to 24,000 characters and output to 1,200 requested tokens/8,000 accepted characters. Reaching a resource cap is partial coverage, not a complete inventory.

## Troubleshooting and cleanup — owner-run

- Startup failure: verify both Secrets/keys exist, target CA is valid, and required model/target settings are set.
- `connection_failed` / TLS failure: confirm target IP is current, app pods can reach it, and `ca.crt` belongs to `target`. Recreated clusters require a fresh IP/CA/token. Do not disable verification.
- `denied`: namespace must match the target Role/RoleBinding. `unauthorized` usually means the temporary token expired.
- Provider unavailable: confirm base URL, model ID, key, compatibility with Chat Completions and pod egress. Error bodies and keys are not returned to the browser or logged.
- Empty complete sources: add a workload in the configured target namespace; the model has no unobserved data.

```sh
helm uninstall vyom-poc --kube-context kind-app --namespace vyom-poc
helm uninstall vyom-reader --kube-context kind-target --namespace demo
```

The Secrets you created separately remain until you remove them. For clusters created only for this POC, remove them when finished:

```sh
kind delete cluster --name app
kind delete cluster --name target
```

Do not run these deletion commands against clusters you want to keep.

## Design sources

Reviewed for this POC: [shadcn Vite setup](https://ui.shadcn.com/docs/installation/vite), [shadcn Button registry](https://ui.shadcn.com/r/styles/new-york/button.json), [Kubernetes ServiceAccounts](https://kubernetes.io/docs/concepts/security/service-accounts/), [token creation](https://kubernetes.io/docs/reference/access-authn-authz/service-accounts-admin/), [Kind quick start](https://kind.sigs.k8s.io/docs/user/quick-start/) and [FastAPI async/HTTPX testing](https://fastapi.tiangolo.com/advanced/async-tests/) and [LangChain ChatOpenAI](https://docs.langchain.com/oss/python/integrations/chat/openai). These references do not prove this POC is deployed. Logo source: [canonical Vyom branding](../../docs/BRANDING.md).
