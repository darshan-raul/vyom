# Decisions

The constitution already specifies the product stack and sprint boundaries; do not duplicate its decision log here. This file records only fresh implementation choices and unresolved inputs. Proposed choices are not authorization or delivered functionality.

| ID | State | Choice / question | Resolve by | Consequence |
|---|---|---|---|---|
| P01 | Resolved by the owner 2026-10-12 and verified live; see [S1.4](#s14-reasoning-adapter--2026-10-12) | OpenRouter at `https://openrouter.ai/api/v1`, model `anthropic/claude-haiku-5.5`; key read through a credential reference (environment variable or ignored file) | Repeat the live check if the model or endpoint changes | Real tool-call compatibility passed 2026-10-12; never ask for a key in chat |
| P02 | Proposed | Fresh directories: `frontend/`, `backend/` (API + agent + MCP client + SDK collectors), `tests/`, `deploy/`, `scripts/` | S1.1 | Create only when used; upstream Kubernetes MCP is a separately pinned image |
| P03 | Open | Available Kind/container tooling and namespace for controlled test workloads | S1.1 | Check local tooling before publishing setup commands |
| P04 | Open | EKS reuse/create, AWS account, IAM provisioning authority, spend budget and teardown owner | S2.1 | No chargeable provisioning inferred from a documentation request |
| P05 | Open | In-region Bedrock model/embedding IDs, access and data-handling checks | S3.1 | Model selection is verified at implementation time |
| P06 | Resolved for Kind by [MCPK01](#s13-upstream-kubernetes-mcp-on-kind--2026-10-12), verified live | Private host-to-upstream transport/authentication and explicit Kubernetes ServiceAccount auth mode | Repeat on EKS in S2.1; harden S6.3 | Verify selected upstream release; no tenant-header trust, token passthrough or model-controlled endpoint |
| P07 | Open | Alpha retention, backup destination, restore objectives and encryption | S5.3 | Backups must be outside cluster; S3 bucket is a possible choice, not mandated here |
| P08 | Open | Jev gateway geography, retention, redaction and benchmark threshold | S4.5 | Default remains disabled unless activation gate passes |
| P10 | Open | Pin observability chart/image versions; validate PVC/storage/retention/compaction, discovery, endpoint controls and private Grafana credentials | S1.9; repeat S2.1 | Initial 48h/100% demo sampling is bounded but unmeasured; no Kafka or HA assumed |
| P11 | Open | Re-estimate S1 and aggregate dates/capacity after clean Kind stack installation | S1.8 | 250h means 12.5 weeks at 20h/week; twelve-week target requires an explicit adjustment |
| P12 | Open | Operator-only versus tenant-visible telemetry access and current-grant enforcement | S6.3 | Keep shared operator stores/Grafana private until exposed surfaces pass isolation/revocation gates |
| P09 | Open | Keycloak realm/client, HTTPS hostname, credential segregation and whether Vault is needed | S6.1 | No old realm IDs or domain assumed |

For each resolved entry record: date, accepted/proposed status, task, decision, reason, alternative, consequences, and evidence. Owner acceptance is required for changes to scope or constitutional constraints; routine implementation details can be decided and documented by the implementing agent.

## Accepted MCP architecture revision — 2026-10-03

Owner decision, recorded in [session 2026-10-03-02](sessions/2026-10-03-02.md) and the constitution:

| ID | State | Decision | Rationale / consequence | Tasks |
|---|---|---|---|---|
| MCP01 | Accepted | Vyom is an MCP host/client; no production custom MCP protocol servers | Replace planned FastMCP ownership with existing client SDK and upstream integrations | S1.1–S1.3 |
| MCP02 | Accepted | Prefer containers/kubernetes-mcp-server, self-hosted in the target cluster with scoped ServiceAccount/RBAC | Pin upstream, restrict read-only tools and private exposure; scope decisions are Vyom's responsibility | S1.3, S1.7, S2.1 |
| MCP03 | Accepted | Use AWS-managed MCP / appropriate AWS-provided capabilities for agent investigations | No general-purpose Vyom AWS wrapper; prove resource tool coverage and scoped workload credentials | S2.1–S2.2 |
| MCP04 | Accepted | Direct SDK/API path for deterministic product work; normal libraries for persistence/internal logic | MCP is not a universal internal protocol; preserve independent failure behavior and shared evidence semantics | S1.4, S2, S3.6, S4.3 |
| MCP05 | Accepted | Later servers plug into the same configured client boundary | No extra GitHub/IaC/FinOps implementation scope now; educational servers stay separate | S1.2, S4.2; domains later |
| MCP06 | Planned implementation of accepted isolation rule | Separate upstream Kubernetes endpoints/ServiceAccounts per tenant grant scope initially; AWS account-bound credentials | Avoid treating a shared broad identity or tenant header as provider authorization; verify before S6 completion | S6.3–S6.4 |

Open integration inputs: select/pin upstream version and safe pod result projection (S1.3); choose supported endpoint authentication/TLS (S1.2); verify AWS endpoint region/data handling, read capabilities and unattended credential renewal (S2.1). Source checks are in [MCP_INTEGRATIONS.md](MCP_INTEGRATIONS.md). These decisions replace only the former MCP ownership/universal collection assumptions, not the six-sprint scope or model-provider schedule.

## Observability scope revision — 2026-10-04

Owner-required Loki, Prometheus, Grafana and OTel tracing are accepted scope in the constitution. Its specified design uses Tempo for traces and Alloy for OTLP/log collection, single-instance PVC-backed stores, private access and two starter dashboards from S1; EKS follows S2 and hardening S5. These are planned, undelivered choices, not measured sizing or deployment evidence. See [design](OBSERVABILITY.md) and [planning session](sessions/2026-10-04-01.md).

S1.9 adds 10 task hours and is a prerequisite of S1.7, while S1.8 remains the live closing gate. Existing task IDs and intelligence gates are preserved. S2–S6 instrumentation, recovery and telemetry authorization are acceptance within their current budgets, subject to re-estimation. Agent analytics over the telemetry stores remains deferred; observer log access never widens MCP permissions.

## Accepted brand asset — 2026-10-04

**BRAND01 — Accepted by owner:** use the supplied blue telescope/helm/clouds logo for Vyom branding, including README, application, diagrams and the future website. The canonical source is [assets/branding/vyom-logo.png](../assets/branding/vyom-logo.png); it is preserved unmodified. [Branding guidance](BRANDING.md) governs reuse and accessibility. This replaces any expectation that the logo must be newly generated after the reset; it adds no site implementation or deployment scope. Source-byte and embedded-diagram verification is recorded in [session 2026-10-04-07](sessions/2026-10-04-07.md).

## Separate local chat POC — 2026-10-04

**POC01 — Accepted by owner:** create an isolated experiment at `learning/kind-chat/`, outside S1–S6, with a shadcn frontend and small FastAPI backend in one Kind cluster querying another. This POC uses direct namespace-scoped Kubernetes REST reads and an OpenAI-compatible model, without RAG, MCP, LangGraph, Refine, persistence or the observability stack. These exclusions apply only to the POC; the constitution and sprint acceptance remain unchanged.

The owner supplies Secrets and runs all Docker, Kind, kubectl and Helm steps. Agent verification is limited to code. Two small charts package the UI/API and the target namespace reader respectively. Credentials stay server-side; TLS verification, fixed namespace authority, bounded status projections and list-only RBAC preserve read-only access. A short-lived target token is reread from its Secret volume each question; model key rotation requires an API restart. [Setup and limitations](../learning/kind-chat/README.md), [verification](sessions/2026-10-04-09.md).

**POC02 — Accepted by owner, 2026-10-04:** use LangChain for this experiment's inference. `ChatPromptTemplate` formats policy, bounded browser history and the question; `ChatOpenAI.ainvoke` performs one compatible Chat Completions call. Kubernetes collection stays deterministic and namespace-scoped, with no RAG or MCP. The request limits, Secret injection and Helm interface are retained. Disable automatic retries and LangSmith tracing; retain response byte/context/output limits and sanitized provider failures. [Code evidence](sessions/2026-10-04-10.md). This revises POC01's inference implementation only.

## S1.1 scaffold tooling — 2026-10-11

**SCAF01 — Accepted by owner (proposed before S1.1 started, owner proceeded without changes):** backend uses `uv` with a committed `uv.lock` on Python 3.13 (`>=3.13,<3.14`); frontend uses npm with `package-lock.json`; the MCP client is the official `mcp` Python SDK used directly, not `langchain-mcp-adapters`, so S1.2 owns validation and limits itself; CI is one GitHub Actions workflow. Resolved versions are in the lockfiles; [evidence](sessions/2026-10-11-02.md). Routing (`react-router`), LangGraph and model libraries are not installed until the tasks that need them.

## S1.9 observability pins and deviations — 2026-10-11

Implementation decisions made while installing the owner-required stack; none changes scope. Evidence: [session 2026-10-11-03](sessions/2026-10-11-03.md); detail: [installed summary](OBSERVABILITY.md#installed-on-kind-in-s19).

| ID | Status | Decision | Why |
|---|---|---|---|
| OBS01 | Accepted (implementation) | Take Loki and Tempo from `grafana-community/helm-charts` (18.15.1 and 3.1.0); kube-prometheus-stack 92.3.0 and `grafana/alloy` 1.13.1 from their existing publishers | The `grafana/*` Loki chart is Enterprise-only and the `grafana/*` Tempo chart is deprecated since early 2026 |
| OBS02 | Accepted (implementation) | Install from checksum-pinned chart archives listed in `deploy/observability/charts.lock`, fetched by one script, instead of a Helm umbrella chart or helmfile | Keeps one reproducible workflow with no extra tool; retried downloads survive this machine's slow GitHub path |
| OBS03 | Accepted (implementation) | Disable Alertmanager, default rules and the bundled dashboards; disable etcd, scheduler, controller-manager, kube-proxy and API-server scrapes | Alerts are S5; the first four cannot be scraped on Kind; API-server series are large for no S1 use. Revisit API-server and control-plane targets on EKS in S2 |
| OBS04 | Accepted (implementation) | Collector log allowlist is the `vyom` and `observability` namespaces; the demo namespace is not collected | Infrastructure log access must not become agent pod-log access. Add the upstream MCP server only after S1.3 confirms its logging is payload-free |
| OBS05 | Proposed, needs owner view before S5 | PVC sizes are not enforced by Kind's provisioner, so S1 storage is bounded by 48-hour retention, Prometheus's 3 GB cap and ingestion limits only | A hard size bound for Loki and Tempo needs a provisioner that enforces capacity (EKS in S2) or size-based retention work in S5 |

## S1.2 MCP host and evidence contract — 2026-10-12

Made while implementing S1.2; none changes scope. Evidence is fixture-only: [session 2026-10-12-01](sessions/2026-10-12-01.md). Detail: [implemented host](MCP_INTEGRATIONS.md#implemented-in-s12).

| ID | Status | Decision | Why / consequence |
|---|---|---|---|
| MCPC01 | Proposed; needs owner view and S1.3 verification against the pinned release | Streamable HTTP to the upstream's internal Service. The host authenticates with the backend's own projected ServiceAccount token issued for a dedicated audience (not the API server's), read from a file reference at every connect. The upstream must validate that token (`require_oauth` with issuer and `oauth_audience`, or an existing authenticating proxy if the release cannot) and must reach Kubernetes with its own ServiceAccount (`cluster_auth_mode = "kubeconfig"`, never the default). TLS is supported by the host (`https` plus optional `ca_file`); cleartext needs an explicit `allow_cleartext` | Upstream documentation read on 2026-10-12 gives `cluster_auth_mode` a default of `passthrough`, which forwards the caller's `Authorization` header to the Kubernetes API. An audience-bound token is rejected by the API server if it is ever forwarded, so a misconfiguration fails closed instead of acting as the backend. No static shared secret, and rotation is automatic. Not verified: that the pinned release validates ServiceAccount tokens this way, and whether Kind uses TLS on this hop |
| MCPC02 | Accepted (implementation) | A tool is callable only if Vyom has a reviewed `ToolSpec` for it, the operator enabled it, and the server advertises it with the reviewed input schema (sha256 of the canonical schema). Upstream descriptions and annotations are not used and not shown to the model | Discovery cannot enable a tool, `readOnlyHint` cannot make one safe, and an upstream upgrade that changes a schema disables the tool until it is reviewed again |
| MCPC03 | Accepted (implementation) | One short MCP session per discover or call, closed afterwards; the schema is checked on the same session just before the call | No pooled session, cached schema or cached credential to isolate or revoke. Costs one extra round trip per call, acceptable for one bounded tool round; revisit if S4 multi-call investigations need it |
| MCPC04 | Proposed; revisit when S1.3 shows what the upstream returns | Item identity is `k8s:<cluster UID>:<namespace>:<kind>:<name>`, the same on both paths. The object UID is carried beside it when the source reports one. Each collection also has its own `ev_…` ID | Every path can supply namespace, kind and name; not every upstream result includes a UID. A recreated pod with the same name keeps its ID and is distinguished by UID and collection time |
| MCPC05 | Accepted (implementation) | Scope arguments (namespace now) are set by the host from the trusted context. A proposed value equal to the trusted one is accepted; any other is refused. Results naming another namespace are discarded as a scope violation | With one configured namespace, intersecting proposed scope with authority means equality |
| MCPC06 | Accepted (implementation) | Log records from the `mcp`, `httpx2`, `httpcore2`, `httpx` and `httpcore` loggers are dropped at the handler; `vyom.mcp` logs the same events with allowlisted fields | Those libraries log endpoint URLs and upstream text. Their debug detail is unavailable in Vyom's logs as a result |
| MCPC07 | Accepted (implementation) | Operator configuration (trusted context and MCP servers) is one JSON file; credentials appear only as `file:/path` or `env:NAME` references | No YAML dependency. Nothing loads the file into the running API yet; S1.5 and S1.7 wire and mount it |

## S1.3 upstream Kubernetes MCP on Kind — 2026-10-12

Owner said "go ahead" after the S1.2 report that listed MCPC01 and MCPC04 as needing a view; both are treated as accepted on that basis, MCPC01 as revised by MCPK01 below. Evidence: [session 2026-10-12-02](sessions/2026-10-12-02.md); detail: [deployed on Kind](MCP_INTEGRATIONS.md#deployed-on-kind-in-s13).

| ID | Status | Decision | Why / consequence |
|---|---|---|---|
| MCPK01 | Accepted (implementation; revises the server half of MCPC01), verified live | Caller authentication is done by `kube-rbac-proxy` v0.23.0 as a sidecar, not by the MCP server. The proxy serves TLS on 8443, accepts ServiceAccount tokens for audience `vyom-mcp` (TokenReview) whose subject is granted the name-only resource `mcpendpoints.vyom.dev/kubernetes` (SubjectAccessReview), and forwards to the server on `127.0.0.1:8080`. The server runs with `cluster_auth_mode = "kubeconfig"` and `bind_address = "127.0.0.1"` | `kubernetes-mcp-server` v0.0.67 refuses to start with `require_oauth = true` and `cluster_auth_mode = "kubeconfig"` together, and its other OAuth modes forward or exchange the caller's token. Consequences: one more pinned image; the pod's ServiceAccount holds cluster-scoped `create` on `tokenreviews` and `subjectaccessreviews` (no resource reads); `/healthz` passes the proxy unauthenticated for kubelet probes; an authenticated caller can also reach the server's `/metrics` and `/stats` |
| MCPK02 | Accepted (implementation); since S1.7 the manifests live in the Vyom chart, `deploy/chart/vyom/`, installed by `scripts/vyom-up.sh` | Plain manifests, not the upstream Helm chart | The chart at the v0.0.67 tag is version 0.1.0 with `appVersion: latest`, and the deployment needs the sidecar and exact RBAC. S1.7 moves these manifests into the one Vyom chart |
| MCPK03 | Accepted (implementation) | Upstream `list_output` stays `table`; Vyom parses the fixed-width table and keeps namespace, name, readiness, status and restart count | The table carries no env values or UIDs, so minimization happens before the result leaves the server; the YAML format returns whole pod objects. Any other shape fails as `invalid_output`. The table has no continuation marker, so a returned list is assumed complete |
| MCPK04 | Accepted (implementation) | TLS on the host-to-proxy hop with a self-signed certificate generated once into `.local/mcp-tls/` (90 days); the host trusts that certificate through `ca_file` | Keeps the bearer token off cleartext without adding cert-manager. Renewal is manual: delete the directory and re-run `scripts/mcp-up.sh`. Revisit for EKS in S2.1 |
| MCPK05 | Accepted (implementation); changes how OBS04 is met | The MCP pod runs in `vyom`, which the collector already reads, so its logs are collected. Checked live at `log_level = 0`: session connect/disconnect lines, "Permission denied - check RBAC permissions for <tool>", and proxy authentication failures naming token audiences; no token, argument, pod name or env value | The logs were being collected for about ten minutes before this check was made; nothing sensitive was found in them. `log_level` 6 and above logs MCP parameters and results and must not be set while the pod is collected |

## S1.4 reasoning adapter — 2026-10-12

Evidence: [session 2026-10-12-03](sessions/2026-10-12-03.md), including the owner's live run of `scripts/model-check.sh`.

| ID | Status | Decision | Why / consequence |
|---|---|---|---|
| P01 | Endpoint and model accepted by owner; key mechanism and data handling proposed | Provider label `openrouter`, endpoint `https://openrouter.ai/api/v1`, model `anthropic/claude-haiku-5.5`. The key is named in configuration by reference, `file:…` (default `.local/model-api-key`, ignored by Git, mode 600) or `env:NAME`, and is read for each request. In the cluster the same reference will point at a mounted Secret (S1.7) | The owner named the endpoint and model. The model ID is listed by the provider with tool support (public model list, read 2026-10-12). Using this endpoint sends questions and projected pod names and statuses from the demo cluster to OpenRouter and the upstream model provider; the constitution limits this path to a non-sensitive development cluster. The owner has not separately confirmed that data handling |
| MODEL01 | Accepted by owner 2026-10-12 ("switch"); replaces a first version that posted requests by hand | The adapter calls the endpoint through LangChain's `ChatOpenAI` (`langchain-openai`, which uses the `openai` client). Callers pass LangChain messages and receive the model's `AIMessage` inside a `Reply` | Matches the constitution's sources and the owner's POCs; LangGraph (S1.5) uses the same message types, and the Bedrock adapter (S3) becomes a different chat model behind the same interface. Cost: `langchain-openai`, `langchain-core`, `openai`, `langsmith` and their dependencies are now installed. Vyom wraps the call to keep its rules: LangSmith export is disabled for every request even if ambient `LANGSMITH_*` settings exist, client-library loggers are dropped, and provider exceptions are reduced to fixed error kinds |
| MODEL02 | Accepted (implementation) | One request per call and no retries (`max_retries=0`); 30 s timeout, 1024 output tokens and a 256 KiB response limit by default. Failures are mapped from the exception class and HTTP status; exception text, which can quote the provider's error body, is never used | Bounded time and cost per question. Consequence: a transient provider failure surfaces as `unavailable` or `rate_limited` and the caller decides what to do. The `openai` client still adds an `OpenAI-Organization` header if `OPENAI_ORG_ID` is set in the environment; do not set it |
| MODEL03 | Accepted (implementation) | The adapter rejects a reply whose tool call is malformed as `malformed_tool_call`: arguments that are not a JSON object (LangChain sets these aside or refuses the message) or a missing ID or name. Whether the tool is allowed and its arguments valid stays with the MCP host | One place decides tool policy. Arguments that are well-formed JSON but wrong for the tool reach the host and are refused there as `invalid_arguments` or `scope_violation` |
| MODEL04 | Accepted (implementation) | Metric labels are the configured provider and model plus a fixed outcome. Token counts are read from the provider's own usage report, not LangChain's `usage_metadata`, which fills a missing report with zeros; a successful reply without usage increments `vyom_model_usage_unavailable_total` | Unavailable is not zero. Provider and model are operator configuration, so the label set is bounded |
| MODEL05 | Accepted (implementation); extends MCPC07 | The operator file gains an optional `model` section. Credential references moved to `vyom/credentials.py` and are shared by the MCP registry and the adapter | One file still describes everything the backend may connect to. Without the section there is no model and chat must report unavailable |

## Frontend design spec — 2026-10-12

Owner supplied `vyom-design-spec.zip` (spec, three mockups, circular logo) and asked for the frontend to be redesigned to it, less dense at first, adapted to AWS + Kubernetes and to the plan. Evidence: [session 2026-10-12-04](sessions/2026-10-12-04.md).

| ID | Status | Decision | Why / consequence |
|---|---|---|---|
| UI01 | Accepted by owner (the request) | [design/DESIGN.md](design/DESIGN.md) is the source of truth for the UI's look: dark-only navy console, status colours only for status, sky blue only for the agent, Archivo + JetBrains Mono, mono identifiers | Replaces the neutral shadcn theme and Geist from S1.1. shadcn components keep working through the token mapping. No light theme |
| UI02 | Proposed; the adaptation is the agent's reading of "tweak it to our requirements" | The spec's scope follows the constitution, recorded in DESIGN.md §0: surfaces arrive with the sprint that serves their data; multi-org, exposure, CVE, compliance, drift, Terraform drafting, savings and forecasts in the mockups are not scheduled | The mockups show features in the constitution's "Keep out" list. Building them needs a constitution change, not a design reference |
| UI03 | Proposed | Planned surfaces are listed in the sidebar and the question-path strip, dimmed, with their sprint, and are not links. No page exists for them | Shows where the console is going without placeholder pages or sample data. Cost: these labels are static and must be updated as each surface lands |
| UI04 | Proposed | The UI shows only what the API serves. With only `/api/health` today, Today reports API liveness; the Ask Vyom panel is disabled and says the chat route is not built | Spec principle 7 and the evidence rule that missing is not zero. S1.5 enables the panel |
| UI05 | Accepted by owner (supplied asset); see [branding](BRANDING.md) | The app uses the supplied circular transparent mark; the canonical logo is unchanged | The canonical PNG has an opaque light background, which the earlier guidance said to place on a light area. The supplied mark removes that need on the dark console |

## S1.5 bounded graph and chat — 2026-10-13

Made while implementing S1.5; none changes scope. Evidence: [session 2026-10-13-01](sessions/2026-10-13-01.md); detail: [chat workflow](MCP_INTEGRATIONS.md#chat-workflow-in-s15).

| ID | Status | Decision | Why / consequence |
|---|---|---|---|
| CHAT01 | Accepted (implementation) | One tool call per question, not only one round: the first proposed call is made, any others in the same reply are answered "not called", and a tool proposal in the answer step ends the question as `tool_round_limit` | The smallest bound that answers the S1 question. S4.2 raises it with explicit call, iteration and time budgets |
| CHAT02 | Proposed; needs owner view | An answer is returned only if it is tied to the evidence: it cites only items that were shown to the model and at least one when items exist. Otherwise it is withheld as `invalid_answer` and the evidence is still returned | "Validate citations" taken strictly: a wrong or absent citation is the only signal available that the model left the evidence. Cost: a correct answer that forgets to cite is withheld. Whether the real model cites reliably is checked by the live gate |
| CHAT03 | Proposed; needs owner view | `POST /api/chat` returns HTTP 200 for every outcome, with an explicit `outcome` and a fixed `limitation` text; only a malformed request is a 4xx | The UI shows one shape for answers and non-answers. Consequence: HTTP status metrics do not show chat failures; `vyom_chat_requests_total{outcome}` and the span status do |
| CHAT04 | Accepted (implementation) | When the model proposes no tool call, whatever it wrote is dropped and the result is `no_tool_used` | The constitution forbids an ungrounded fallback. Consequence: greetings and general questions get the fixed limitation |
| CHAT05 | Accepted (implementation); extends MCPC07 | The API reads the operator file named by `VYOM_CONFIG` at start. Without it the API runs with health only and chat answers `not_configured`. `GET /api/agent` shows scope, model ID and enabled tool IDs to the browser | The browser needs to show scope and tools without choosing them. Nothing in that response is a credential or an endpoint URL |

## S1.6 direct Kubernetes view — 2026-10-13

Made while implementing S1.6; none changes scope. Evidence: [session 2026-10-13-02](sessions/2026-10-13-02.md); detail: [direct pod view](MCP_INTEGRATIONS.md#direct-pod-view-in-s16).

| ID | Status | Decision | Why / consequence |
|---|---|---|---|
| K8S01 | Accepted (implementation) | The collector calls the Kubernetes API over HTTPS with `httpx` and asks for the server's Table rendering with `includeObject=Metadata`, not the official Python client and not full pod objects | Minimization happens at the source: no pod spec or env value reaches Vyom, checked live. Status, readiness and restarts are computed by the API server, so they equal kubectl and the MCP table. No new dependency. Consequence: only what the Table carries is available; S2.3's waiting and termination reasons will need another projection |
| K8S02 | Resolved 2026-10-18; see [S1.7](#s17-kind-packaging--2026-10-18) | In development the collector's token comes from `kubectl create token vyom-collector`. How the in-cluster API pod holds this second identity is not decided | A pod has one ServiceAccount. Options: mount a token Secret for `vyom-collector` (separate identity, long-lived token), or grant the read to `vyom-api` (one identity for the MCP endpoint and the collector, and `mcp-check.sh` currently asserts it has no Kubernetes access), or run the collector as its own workload |
| K8S03 | Accepted (implementation) | `GET /api/kubernetes/pods` reads the cluster on each request; nothing is cached or stored, and the page polls every 15 seconds | Simplest correct freshness for one user and one namespace. Scheduled observation and history are S3.6 |
| K8S04 | Proposed | The UI uses `react-router` for its two routes, without Refine's router binding or resources | Two pages need addresses. Refine's resource routing is not needed until there are list and detail views to generate |


## Owner answers — 2026-10-18

| ID | State | Choice | Consequence |
|---|---|---|---|
| P01 | Answered by owner 2026-10-18 | Data sent to OpenRouter is redacted of sensitive details first. Bedrock (P05, S3.1) is the intended later provider so model traffic stays inside the AWS account | Redaction rules are not yet specified or implemented; the current projection (pod names, namespace, status, readiness, restarts; no env values or specs) is the baseline. Specify the redaction list before any non-demo cluster is connected |
| K8S02 | Answered 2026-10-18 (resolution recorded in the S1.7 section below): the collector's token is mounted into the `vyom-api` pod as a file (separate identity from the MCP identity) | Rotation: approach B chosen 2026-10-18. A CronJob with its own ServiceAccount (create on `serviceaccounts/token` for `vyom-collector` only; update on the one named Secret only) writes a fresh 1-hour token to the Secret every 30 minutes; the API re-reads the file on each request. Built in S1.7 | `mcp-check.sh`'s assertion that `vyom-api` has no Kubernetes access stays valid |
| CHAT02, CHAT03 | Deferred by owner 2026-10-18 to the next phase | Current behaviour stands (strict citation check; HTTP 200 for every outcome) | Revisit before S2 |
| UI02 | Owner: skip (mockup-only features stay unscheduled) | As recorded | None |
| UI03 | Accepted by owner 2026-10-18 | As recorded | Update sprint labels as surfaces land |
| UI04, K8S04, MCPC01 (as revised by MCPK01), MCPC04 | Accepted by owner 2026-10-18 | As recorded | None |

## S1.7 Kind packaging — 2026-10-18

| ID | State | Choice | Consequence |
|---|---|---|---|
| K8S02 | Resolved by the owner 2026-10-18 (mount as a file; approach B for rotation) | The collector's token is a file mounted from Secret `vyom-collector-token`. CronJob `vyom-collector-token-refresh` runs `python -m vyom.token_refresher` from the API image every 30 minutes as ServiceAccount `vyom-token-refresher`, which may create tokens for `vyom-collector` only and patch that one Secret only. Tokens last one hour. `vyom-api` keeps no Kubernetes access | A kubectl image was rejected because it has no shell, so a token could not be piped into a patch. The refresher is about 50 lines of Vyom code with two tests. The kubelet can take about a minute to show a patched Secret in a running pod; the half-hour margin covers it, and `vyom-up.sh` waits for the first token. If the refresher stops, the pods view reports `denied` within an hour |
| PKG01 | Accepted (implementation) | Vyom builds two images, API and UI, with `docker build` from `backend/Dockerfile` and `frontend/Dockerfile`; base images are pinned by digest in `deploy/images.lock`; tags are a hash of the source tree; images are loaded into Kind (`kind load`, with an archive fallback). No registry | Nothing is pushed anywhere. Moving to EKS (S2.1) needs a registry decision. The first build takes about ten minutes (Python dependencies); an unchanged tree reuses the loaded image |
| PKG02 | Accepted (implementation) | The UI image is nginx serving the build and forwarding `/api` to the `vyom-api` Service, so the browser talks to one origin | A localhost port-forward to `vyom-ui` is the only entry point. The `/api` forward has a 90 s read timeout over the API's 60 s chat deadline |
| PKG03 | Accepted (implementation) | Secrets (`kubernetes-mcp-tls`, `vyom-model-key`, `vyom-collector-token`) are created by `vyom-up.sh` from local files, not by the chart and not from values. The model key Secret is optional in the pod | No credential in Helm values or release history (checked by `vyom-check.sh`). Without a key the API starts and chat says the credential is missing |
| PKG04 | Accepted (implementation) | `VYOM_MODE` unset or `production` makes `vyom.api.app` raise `DevelopmentIdentityRefused` on import; only `development` builds the app with the fixed resolver. The chart and the dev and live-check scripts set `development` explicitly | Production mode cannot start at all until S6 adds a verifying resolver, which is the intended reading of "rejects the development identity". Any script that imports the app must set the mode |
| MCPK06 | Accepted (implementation), verified live | `loopback_host_header: true` in the server entry of the operator file makes the host send `Host: localhost`. The upstream's Go MCP SDK answers 403 to a non-localhost Host on a connection that arrives over loopback, and the sidecar proxy always delivers over loopback (MCPK01). `MCPGODEBUG=disablelocalhostprotection=1` was tried first and has no effect in the SDK version the server was built with | TLS verification still uses `kubernetes-mcp.vyom.svc`. The check protects browsers against DNS rebinding; no browser can reach this endpoint, and the proxy authenticates every caller first. The option is per server and defaults off |
| PKG05 | Accepted (implementation) | The release namespace is `vyom`; the MCP URL in the operator file and the certificate names assume it. The ServiceMonitor is created only if its CRD exists (`vyom-up.sh` checks) | A different namespace needs the URL and certificate changed. Install observability first for the scrape |

## S1.8 live gate — 2026-10-18

| ID | State | Choice | Consequence |
|---|---|---|---|
| GATE01 | Accepted (implementation) | `vyom-down.sh` removes the release, Vyom's Secrets and namespace `demo`, but keeps namespace `vyom`. `vyom-up.sh` warns if Alloy has no Role there | Alloy's log-discovery Role lives in `vyom` and belongs to the observability install. Deleting the namespace made log collection fail silently after the next Alloy restart; the gate found it |
| GATE02 | Accepted (implementation) | The gate reads Grafana, Loki, Tempo and Prometheus through localhost port-forwards and the Grafana links through Grafana's own API; stored signals are checked by dumping them to `.local/s18/` and scanning locally, including for the model key, which is never sent to a query | A Loki query containing the key would write it into Loki's own logs. The two navigation links are proven through the API, not clicked in the UI |
| GATE03 | Accepted (observation) | Telemetry loss is bounded and visible, not prevented: with Alloy stopped the outage spans are dropped (the question is not slowed), log lines are recovered from the saved read position, and `kube_daemonset_status_number_ready{daemonset="alloy"}` shows the outage; with Tempo stopped the lost spans are counted in `otelcol_exporter_send_failed_spans_total` | There is no application-side metric for spans the API itself drops when its 512-span queue is full; add one if that ever matters |


## Accepted product rescope — 2026-10-29

Owner specification replaces pending six-sprint scope with Inventory, Investigation and Security. Cost/FinOps is excluded; RAG/Qdrant is deferred; Postgres inventory precedes investigation expansion; AWS waits for the Kubernetes vertical slice. Full telemetry is optional target architecture, with packaging decoupling pending. See [audit](RESCOPE_AUDIT.md). Earlier conflicting decisions are superseded, not deleted.

## R1 continuation — 2026-10-29

Owner instruction: README always describes the intended final product, without completion or future-work commentary. Status and limitations belong in tracker/handoff; setup in LOCAL_DEVELOPMENT. Implementation choice: app defaults to no telemetry stores; explicit metrics/full profiles enable scraping, and only full enables trace export. Metrics vendor install excludes Grafana; existing optional releases are not automatically removed. Live profile validation remains pending.

## Continuous operations — 2026-10-29

Accepted by owner: extend Vyom into a continuous operations station while preserving Inventory, Investigation and Security, natural-language questions and read-only infrastructure access. Deterministic observations/conditions create issues; bounded agents investigate. Security findings and external detections do not alone establish confirmed incidents. First automatic loop follows manual Kubernetes workload diagnosis; AWS waits for that gate. See [design and acceptance](CONTINUOUS_OPERATIONS.md). Postgres job leases, episode fingerprints and lifecycle details are implementation design choices to validate, not claims of runtime capability. No calendar estimate or chargeable infrastructure authorization is implied.

## Roadmap consolidation — 2026-10-29

Implementation of the accepted overhaul: the legacy constitution filename is retained for links, but its content is the active product constitution without reset commands or fixed sprint dates. R1–R10 replace superseded pending S tasks; completed evidence stays linked. Documentation validation checks active dependencies, status and evidence. History is never execution authority. Kind setup rejects non-Kind contexts and honors custom cluster names. Local verification explicitly omits model credentials and targets the new vyom cluster; the user's apollo11 context is restored.

## Overhaul review — 2026-10-29

Accepted by owner (session 08): the constitution file is renamed `CONSTITUTION.md`; the twelve-week filename was kept only for links and misled readers. RESCOPE_AUDIT is frozen as a snapshot; the plan alone owns delivery order and the change map no longer repeats it. All cluster scripts share `vyom-up.sh`'s rule that only `kind-*` contexts are accepted. No scope change.
