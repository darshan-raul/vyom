# Decisions

The constitution already specifies the product stack and sprint boundaries; do not duplicate its decision log here. This file records only fresh implementation choices and unresolved inputs. Proposed choices are not authorization or delivered functionality.

| ID | State | Choice / question | Resolve by | Consequence |
|---|---|---|---|---|
| P01 | Open | Initial OpenAI-compatible endpoint, model, API-key injection and acceptable development data processing | S1.4 | Real tool-call compatibility must pass; never ask for a key in chat |
| P02 | Proposed | Fresh directories: `frontend/`, `backend/` (API + agent + MCP client + SDK collectors), `tests/`, `deploy/`, `scripts/` | S1.1 | Create only when used; upstream Kubernetes MCP is a separately pinned image |
| P03 | Open | Available Kind/container tooling and namespace for controlled test workloads | S1.1 | Check local tooling before publishing setup commands |
| P04 | Open | EKS reuse/create, AWS account, IAM provisioning authority, spend budget and teardown owner | S2.1 | No chargeable provisioning inferred from a documentation request |
| P05 | Open | In-region Bedrock model/embedding IDs, access and data-handling checks | S3.1 | Model selection is verified at implementation time |
| P06 | Open | Private host-to-upstream transport/authentication and explicit Kubernetes ServiceAccount auth mode | S1.2; harden S6.3 | Verify selected upstream release; no tenant-header trust, token passthrough or model-controlled endpoint |
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

**POC01 — Accepted by owner:** create an isolated experiment at `poc/kind-chat/`, outside S1–S6, with a shadcn frontend and small FastAPI backend in one Kind cluster querying another. This POC uses direct namespace-scoped Kubernetes REST reads and an OpenAI-compatible model, without RAG, MCP, LangGraph, Refine, persistence or the observability stack. These exclusions apply only to the POC; the constitution and sprint acceptance remain unchanged.

The owner supplies Secrets and runs all Docker, Kind, kubectl and Helm steps. Agent verification is limited to code. Two small charts package the UI/API and the target namespace reader respectively. Credentials stay server-side; TLS verification, fixed namespace authority, bounded status projections and list-only RBAC preserve read-only access. A short-lived target token is reread from its Secret volume each question; model key rotation requires an API restart. [Setup and limitations](../poc/kind-chat/README.md), [verification](sessions/2026-10-04-09.md).

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

