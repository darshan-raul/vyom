# MCP integration contract

MCP is the agent-facing integration boundary. Native inventory collection, recurring polling, dashboards, rule execution and persistence use normal APIs/libraries. The host selects registered endpoints and private credentials, validates reviewed tool schemas/arguments/results, enforces current scope and bounded execution, and records sanitized evidence. Upstream servers do not interpret Vyom tenant headers; provider identities and isolated sessions enforce scope.

Keep the pinned upstream Kubernetes server and proxy in the application chart. Add tools only with the consuming investigation skill and deny unreviewed discovery. Separate direct collector, MCP provider, MCP caller and log observer identities. No arbitrary shell, SQL, exec, writes, Secret values or unrestricted log/event bodies. Metadata projection is not a provider RBAC field restriction.

For AWS, select a suitable AWS-managed/provided integration only in R7 after native inventory exists. Verify actual endpoint/auth/tool coverage at implementation time; documentation endpoints and direct inventory do not prove live MCP integration. Do not build a general AWS wrapper to hide missing upstream capability. Consuming existing analysis results does not authorize starting paid analysis.

R10 enforces current grants for historical and live evidence and in-flight jobs; credentials/sessions cannot cross authorized connections. Development remains localhost/internal with fixed operator context. See [architecture](ARCHITECTURE.md), [verification](VERIFICATION.md) and [setup](LOCAL_DEVELOPMENT.md).

## Existing implementation reference

The following S labels identify historical implementation evidence, not active delivery order. Name-based transient resource IDs must be migrated before durable inventory; absence of a UID or continuation marker cannot prove identity continuity or authoritative deletion. The current one-tool chat is not the workload investigation skill.

## Implemented in S1.2

Host side only, proven against an offline fixture server; no upstream Kubernetes MCP server has been contacted. Code is in `backend/src/vyom/`.

- **Evidence contract** (`evidence.py`): `build_evidence` is the single constructor for both paths. Evidence carries a collection ID, source (trusted scope plus either MCP server/tool/upstream identity or a direct collector name), host-clock UTC collection time, coverage, projected items and errors with fixed text. States are `complete`, `zero`, `partial`, `stale`, `denied` and `missing`; `stale` is decided by the reader's freshness budget. A source timestamp is present only when the source supplied one.
- **Trusted context** (`context.py`): workspace, connection, cluster UID and one namespace, from operator configuration behind a resolver that R10 replaces.
- **Registry** (`mcp_client/registry.py`): servers with ID, bound connection, URL without credentials or query, credential reference, enabled upstream tool names and limits (connect and call time, response bytes).
- **Host** (`mcp_client/host.py`): `discover(server_id)` and `call(tool_id, arguments, context)`. Tool IDs are `<server>__<tool>`. Each operation opens and closes its own session. The host sends only its own credential, stops reading a response at the byte limit, applies one deadline, validates typed arguments with unknown fields refused, sets scope arguments itself, checks the advertised schema against the reviewed digest, projects the result and returns evidence. Transport exception groups, HTTP 401/403, timeouts, oversized bodies, schema mismatch and unexpected shapes each map to their own error kind.
- **Tool definitions** (`mcp_client/tools.py`): a `ToolSpec` holds Vyom's description, the argument model, the reviewed schema digest, the projector, scope arguments and an item limit. None is registered for a real server yet.
- **Telemetry**: spans `mcp.client.discover`, `mcp.client.call` and `evidence.normalize`; `vyom_mcp_client_operations_total{server,tool,operation,outcome}` and `vyom_mcp_client_operation_duration_seconds{server,tool,operation}`; one `vyom.mcp` log line per operation. Unconfigured server or tool names are recorded as `unlisted`. The SDK adds its own `MCP send …` client spans and W3C context in request metadata.

The API loads the operator file from S1.5 (`VYOM_CONFIG`); S1.7 mounts it in the cluster.

## Chat workflow in S1.5

`backend/src/vyom/agent/graph.py` is a LangGraph graph with three steps and no loop. The host stays the only place that decides tool policy.

| Step | What happens | Ends early with |
|---|---|---|
| `propose` | The model sees the question, a system prompt naming the configured namespace, and the host's enabled tools (Vyom's descriptions, scope arguments not offered) | `model_unavailable`; `no_tool_used` when the model proposes no call (whatever it wrote instead is dropped) |
| `collect` | The first proposed call goes to `McpHost.call` with the trusted context; further calls in the same reply are answered "not called" without reaching the host. The model is shown a projection of the evidence: state, collection time, completeness, error texts and up to 50 items, each with a ref number | `no_evidence` when the call was refused or failed (no second model request) |
| `answer` | The model answers from that projection. A second tool proposal is refused. The answer must be non-empty, not cut off, cite only refs that were shown, and cite at least one when items exist | `tool_round_limit`, `invalid_answer`, `model_unavailable` (the collected evidence is still returned) |

- One deadline (60 s) covers the whole question: `timeout`.
- `POST /api/chat` accepts `{"question": "..."}` only (1–500 characters; any other field is a 422) and returns `outcome`, `answer` or `limitation`, `citations` (ref → evidence ID and item ID), the full `evidence` and the request's `trace_id`. Every outcome is HTTP 200.
- `GET /api/agent` returns what is configured: scope (connection and namespace), model provider and ID, enabled tool IDs. It probes nothing.
- There is no other read path in the workflow. When MCP fails the answer is `no_evidence`; nothing switches to an SDK.
- Telemetry: spans `chat.graph`, `graph.propose`, `graph.collect`, `graph.answer` above the existing model-client and MCP-client spans, in the request's trace; `vyom_chat_requests_total{outcome}`, `vyom_chat_duration_seconds`, `vyom_graph_step_duration_seconds{step}`; one `vyom.chat` log line per question with the outcome. No question, answer or evidence content in any of them.

Run it locally with `scripts/dev-up.sh`; verify it live with `scripts/chat-check.sh`.

## Direct pod view in S1.6

The deterministic path, in `backend/src/vyom/collectors/kubernetes.py`. It shares the evidence contract with the MCP path and nothing else: no MCP host, no model, no shared credential.

- **Identity.** ServiceAccount `vyom-collector` ([identities.yaml](../deploy/chart/vyom/templates/identities.yaml)), allowed `list` on pods in `demo` only. It is neither the MCP server's identity (`kubernetes-mcp`) nor the identity the backend presents to the MCP endpoint (`vyom-api`, which still has no Kubernetes access).
- **Request.** `GET /api/v1/namespaces/<namespace>/pods` with `Accept: application/json;as=Table;g=meta.k8s.io;v=v1` and `includeObject=Metadata`, paged by 100. The API server renders the same Ready, Status and Restarts values `kubectl get pods` prints and attaches object metadata only, so pod specs and literal environment values are never sent to Vyom. The namespace comes from the trusted context.
- **Evidence.** `path: direct`, `collector: kubernetes-pods`, the same resource ID as the MCP path (`k8s:<cluster UID>:<namespace>:pod:<name>`), plus the pod UID, which the MCP table does not carry. A failed later page leaves `partial` evidence; more than `max_items` (500) is cut and marked truncated.
- **Failures.** 401 → `auth`, 403 → `forbidden` (both `denied`), unreachable → `unavailable`, slow → `timeout`, unexpected shape → `invalid_output`, oversized page → `oversized` (all `missing`). An empty namespace is `zero`.
- **Route.** `GET /api/kubernetes/pods` returns `{configured, evidence}` and reads the cluster on each request. Without a `kubernetes` section in the operator file it returns `configured: false`.
- **Telemetry.** Span `collector.kubernetes.pods` with `evidence.normalize`; `vyom_collector_runs_total{collector,outcome}`, `vyom_collector_duration_seconds{collector}`, `vyom_collector_last_success_timestamp_seconds{collector}`; one `vyom.collector` log line per run. No resource name or UID in any of them.

Verify it live with `scripts/pods-check.sh`.

## Deployed on Kind in S1.3

`scripts/vyom-up.sh` installs the [chart](../deploy/chart/vyom/) (since S1.7; S1.3 applied plain manifests), which holds the [server settings](../deploy/chart/vyom/files/kubernetes-mcp.toml), and applies the [demo workloads](../deploy/kind/demo.yaml); `scripts/mcp-check.sh` verifies the result live through a localhost port-forward.

| Item | Value |
|---|---|
| MCP server | `quay.io/containers/kubernetes_mcp_server@sha256:e47f6ccc5347e1ea6be495d8d9ab55ac8a995fe87800fb984fa770cebe14ad44` (v0.0.67, 2026-09-18) |
| Authenticating proxy | `quay.io/brancz/kube-rbac-proxy@sha256:a6075902738eaf1780390561ea998a53a056ef1d2b312bcbf0e2e81fec084b3c` (v0.23.0, 2026-09-24) |
| Placement | One Deployment `kubernetes-mcp` in `vyom`, two containers; Service `kubernetes-mcp` ClusterIP port 8443 |
| Server settings | HTTP on `127.0.0.1:8080`, stateless, `log_level = 0`, in-cluster provider, `cluster_auth_mode = "kubeconfig"`, `read_only = true`, toolset `core`, `enabled_tools = ["pods_list_in_namespace"]`, Secrets in `denied_resources` |
| Kubernetes identity | ServiceAccount `kubernetes-mcp`: `list` on pods in `demo` only, plus `create` on `tokenreviews` and `subjectaccessreviews` for the proxy |
| Caller identity | ServiceAccount `vyom-api` (no Kubernetes read access), token audience `vyom-mcp`, granted `mcpendpoints.vyom.dev/kubernetes` in `vyom` |
| Negotiated protocol | `2026-07-28`; the server reports name `kubernetes-mcp-server` and an empty version |
| Reviewed tool | `kubernetes__pods_list_in_namespace`, input-schema sha256 `1c2a5fed…e394d` in `backend/src/vyom/mcp_client/kubernetes.py`; the model may set `labelSelector` only |

Why a proxy: v0.0.67 does not start with `require_oauth = true` and `cluster_auth_mode = "kubeconfig"` together ([MCPK01](DECISIONS.md#s13-upstream-kubernetes-mcp-on-kind--2026-10-12)). The token the backend presents is refused by the Kubernetes API itself (wrong audience), and a denied list names `system:serviceaccount:vyom:kubernetes-mcp` as the actor, so the caller's credential is not the Kubernetes identity.

## Vyom chart on Kind in S1.7

`scripts/vyom-up.sh` builds the API image (`backend/Dockerfile`, Python 3.13, non-root, uv-locked dependencies) and the UI image (`frontend/Dockerfile`, nginx serving the build and forwarding `/api` to the API Service), loads both into Kind, creates three Secrets from local files and installs [deploy/chart/vyom](../deploy/chart/vyom/). Base images are pinned by digest in [images.lock](../deploy/images.lock). Nothing is published on host ports.

| Workload | Identity | What it can do |
|---|---|---|
| `vyom-api` | ServiceAccount `vyom-api`, no automounted token | Use the MCP endpoint (a projected token for audience `vyom-mcp`, renewed by the kubelet). No Kubernetes read access |
| `vyom-api` reading pods directly | Token of `vyom-collector`, mounted as a file from Secret `vyom-collector-token` | List pods in `demo` only |
| `kubernetes-mcp` (server and proxy) | ServiceAccount `kubernetes-mcp` | List pods in `demo`; create TokenReviews and SubjectAccessReviews |
| CronJob `vyom-collector-token-refresh` | ServiceAccount `vyom-token-refresher` | Mint tokens for `vyom-collector` and patch the one Secret; nothing else |
| `vyom-ui` | none | Serves the UI and forwards `/api` |

**Collector token ([K8S02](DECISIONS.md#s17-kind-packaging--2026-10-18)).** The API pod's own account cannot read pods, so the refresher (`python -m vyom.token_refresher` in the API image) asks the API server for a one-hour token for `vyom-collector` every 30 minutes and patches it into the Secret. The API re-reads the file on each request. The kubelet may take up to a minute to show a patched Secret inside a running pod, which the half-hour margin covers. The Secret is created empty by `vyom-up.sh`, not by the chart, so a token never enters Helm's release history.

**Secrets made by the script, never from chart values:** `kubernetes-mcp-tls` (certificate generated into `.local/mcp-tls/`; the API pod mounts only `tls.crt` as `ca_file`), `vyom-model-key` (optional), `vyom-collector-token`.

**Production mode.** `VYOM_MODE` unset or `production` makes the API refuse to start (`DevelopmentIdentityRefused`), because the only identity resolver is still the fixed development one. The chart sets `development`; R10 adds a resolver that verifies callers.

**Host header ([MCPK06](DECISIONS.md#s17-kind-packaging--2026-10-18)).** The upstream server refuses a request that reaches it over loopback with a non-localhost `Host`, which is how the sidecar proxy delivers every call. The operator file therefore sets `loopback_host_header: true` for this server and the host sends `Host: localhost`; TLS is still verified against `kubernetes-mcp.vyom.svc`.

Verify with `scripts/vyom-check.sh` (21 checks); tear down with `scripts/vyom-down.sh`, which keeps namespace `vyom` because Alloy's log-discovery Role lives there ([GATE01](DECISIONS.md#s18-live-gate--2026-10-18)).
