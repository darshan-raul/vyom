# Vyom — Current-State Inventory and Delivery Roadmap

> Status date: 2026-09-19
> Inference inventory updated 2026-10-03: B1.8 adapter refactor; see [`INFERENCE.md`](INFERENCE.md). Other inventory rows retain the original snapshot date.
> Delivery order: **AWS first, then GCP, then Azure**.  
> This is the execution roadmap. Existing `F1.x`/`F2.x`/`F3.x` tracker IDs remain useful as domain-backlog references, but their original all-cloud-at-once ordering is superseded by the release sequence below.

## AWS + Kubernetes first-release beta

The first user is the project owner, using a personal AWS account as a tenant account. The goal is a reliable read-only operations cockpit that answers: **what changed, what costs more, and what needs attention?** On 2026-10-03 the owner expanded the first release to Kubernetes inventory, topology, health/events, and configuration posture across EKS, AKS, GKE, and self-managed clusters. The original three-month AWS-only estimate needs rebaselining. GCP/Azure cloud-provider parity follows AWS; their Kubernetes clusters use the common Kubernetes API connector first.

| Area | Beta commitment |
|---|---|
| Environments | Kind is the reproducible local/CI target; EKS runs only in `ap-south-1` in a dedicated Vyom platform AWS account. The personal AWS account is monitored separately; its resources may be global or in other AWS regions. Public beta access uses the provisional base domain `cc.darshanraul.me` through HTTPS only. |
| Persistence | Postgres, Qdrant, Vault, Keycloak, and workers are self-managed Kubernetes workloads with persistent storage. Bedrock supplies reasoning/embeddings; D34 permits optional external Jev classification via Vercel. Customer EventBridge/SQS are ingestion integrations, not managed persistence. |
| Backup/recovery | Velero stores Kubernetes metadata and EBS volume snapshots in a dedicated encrypted `ap-south-1` S3 bucket. Native Postgres, Qdrant, and Vault backups also go there; scheduled restore drills prove recovery. S3 is backup-only. |
| Connections | Both live AWS and clearly-labelled simulated AWS connections. Floci plus deterministic fixtures cover normal, anomaly, authorization, throttling, and partial-failure paths. |
| Identity | Self-hosted Keycloak. Verified `sub` identifies a user; Postgres `users`, `tenants`, and `memberships` resolve the tenant and role. A user may access only tenants to which the operator assigned membership, and therefore only those tenants' cloud accounts. One active tenant is resolved server-side per request; clients cannot choose or override it. |
| User access | Invite-only beta. The operator provisions Keycloak users and memberships; public self-signup is disabled. |
| Onboarding | A Keycloak-authenticated `vyom` CLI generates pinned OpenTofu config, validates it, and supports explicit user-run apply. A GitHub App may create a user-approved PR later; only installation IDs are tenant-scoped. |
| AWS access | Read-only only. The CLI sends the newly-created least-privilege connector key to tenant Vault once; neither the backend nor CLI retrieves stored AWS secrets or keeps tenant GitHub PATs. |
| Live reflection | CloudTrail management events and Security Hub findings flow through EventBridge → SQS → an EKS worker using IRSA, DLQ, and idempotent consumers. Daily snapshots reconcile missed events. |
| Cost | Cost Explorer history and anomaly inputs are daily, persisted data. Billing is never represented as real-time. |
| Inventory | EC2, EBS, S3, RDS, Lambda, load balancers, ECR, VPC/subnets/security groups/route tables, CloudTrail config, and Route 53 zones/records. EKS identity supports cluster correlation; ECS remains deferred. |
| Kubernetes | Separate read-only Kubernetes API collection for EKS/AKS/GKE/self-managed clusters: onboarding, inventory, relationships, workload health/events, and bounded configuration posture. Tenant → cluster → namespace grants and separate cluster-wide permissions; optional outbound collector for private clusters. B11 remains pending implementation. |
| Security | Security Hub where enabled, supplemented by read-only checks for public S3, permissive security groups, and CloudTrail health. |
| Data lifecycle | 13 months normalized cost/inventory/finding history; 30 days raw event payloads; tenant-admin deletion requests complete within 30 days. Platform storage remains in `ap-south-1`; D34 separately governs external request classification. |
| AI | Bedrock reasoning/embeddings in `ap-south-1`, using configurable allowlisted in-region candidates with zero retention, no cross-region inference, and no invocation-content logging. Select the lowest-cost pair passing policy/grounding evaluation. Optional actual Jev intent classification through Vercel AI Gateway is the D34 external-processing exception, gated by B8.6. Application prompts are minimized/redacted; tenant content is never used for Vyom model training. |
| Chat corpus | No tenant document uploads in beta. Chat uses only authorized AWS/Kubernetes tool results and curated Vyom runbook text. |
| Explicitly deferred | SCA, formal compliance/evidence, advanced FinOps recommendations/commitments, Kubernetes historical metrics/cost allocation/rightsizing, Slack automation, GCP/Azure cloud-provider parity, write remediation, ECS discovery, and full logs/traces/packet analytics. |

The beta exit gate is: the owner can log in to EKS, connect the personal account safely, see simulated and live data without ambiguity, observe an AWS change within minutes, review daily cost movement and Security Hub/direct findings, and receive cited answers from read-only chat. Closure additionally requires the locked scorecard: three active tenants, each onboarded in under 30 minutes; at least two users returning weekly for three consecutive weeks; and one actionable signal per user. The longer R0–R6 plan remains the post-beta path.

The executable, task-level tracker for this beta is [`BETA_EXECUTION_PLAN.md`](BETA_EXECUTION_PLAN.md). Agents must update its task status and evidence at the same time as the invocation tracker in `AGENTS.md`; the R0–R6 sections below remain the long-term dependency and scope reference. Kubernetes B11.8 is now an additional prerequisite for the first-release B9.5 gate: authorized cluster onboarding, topology, health/events, configuration posture, denial/failure paths, and flavor-specific support evidence must pass. See [`KUBERNETES.md`](KUBERNETES.md) for staged coverage and allocation boundaries.

## 1. What “complete” means

Vyom reaches v1 completion when a tenant can onboard multiple AWS accounts, multiple GCP projects, and one Azure tenant; use all supported domains through the UI and agent; and receive tenant-isolated, cited, auditable results in a production-capable Kubernetes deployment.

The v1 domains are:

1. Cost
2. Inventory
3. FinOps
4. Security posture
5. SCA
6. Compliance
7. Alerts

The v1 platform also includes OIDC authentication, tenant-scoped authorization, Vault-backed credentials, persisted history, RAG, the LangGraph agent, observability, automated tests, backup/restore, and operational runbooks.

### Status vocabulary

| Status | Meaning |
|---|---|
| In place | Concrete implementation exists and is broadly aligned with the target |
| Partial | Useful scaffold exists, but it is incomplete or not connected end to end |
| Placeholder | UI, manifest, or documentation exists without the required runtime capability |
| Missing | No meaningful implementation exists yet |
| Conflicting | Existing pieces disagree and cannot work together without a decision or repair |

## 2. Repository inventory

### 2.1 Product and architecture

| Area | Status | What exists now | Gaps / observations |
|---|---|---|---|
| Product definition | In place | `README.md`, phased scope, domain map, exit criteria | Some claims describe target state as current capability |
| Architecture | Partial | Service topology and intended provider abstraction in `docs/ARCHITECTURE.md` | Provider abstraction, agent service, alerts service, and most domain implementations do not exist |
| Decision log | In place | D1–D12 in `AGENTS.md` | Tenant identity model and browser-to-MCP API boundary still need explicit decisions |
| Legacy documentation | Conflicting | `docs/ARCHITECTURE_PLAN.md` remains | It describes the superseded Streamlit architecture and stale phase completion |
| Runbooks | Partial | Local setup and extension notes | No tenant bootstrap, credential rotation, backup/restore, incident, upgrade, or rollback procedures |

### 2.2 Web application (`app/`)

| Capability | Status | What exists now | Gaps / observations |
|---|---|---|---|
| Vite/React/TypeScript shell | Partial | Vite config, TypeScript config, Tailwind, Docker multi-stage build, nginx | No lockfile; local build cannot run until dependencies are installed; known source-level TypeScript inconsistencies remain |
| Refine integration | Partial | `Refine`, router, resources, data-provider scaffold | Resource/data-provider conventions do not match the backend protocols |
| shadcn-style components | In place | Buttons, cards, tables, tabs, forms, layout primitives | Component coverage will need to grow with domain workflows |
| Navigation and layout | Partial | Routes and sidebar for all planned domains | Phase 2/3 routes point to placeholders |
| Authentication UI | Conflicting | Keycloak JS, PKCE configuration, auth provider, guards | Import mismatch in auth source; realm/client/redirect configuration disagrees across app and Keycloak manifests |
| Authorization UI | Partial | `viewer`/`operator`/`admin` route guards | Keycloak realm currently defines a different role set; backend enforcement is absent |
| Overview | Placeholder | Four KPI cards and a fetch call | `/tools/overview/summary` does not exist |
| Costs | Partial | Filters, chart, table, MCP-looking request | Endpoint/tool name and response schema do not match the MCP server |
| Inventory | Partial | Filters and resource table | Endpoint/tool name and normalized resource schema do not match the MCP server |
| Chat | Placeholder | Vercel AI SDK chat surface with tool-call display | No agent endpoint; token lookup uses session-storage keys that auth does not populate |
| Settings | Placeholder | Read-only identity and credential location text | No onboarding, provider connection status, validation, or rotation workflow |
| FinOps | Placeholder | Phase card | No backend or data flow |
| Security | Placeholder | Phase card | No backend or data flow |
| SCA | Placeholder | Phase card | No upload or backend flow |
| Compliance | Placeholder | Phase card | No framework/control flow |
| Alerts | Placeholder | Phase card | No alerts service or rule flow |

### 2.3 MCP server (`mcp-server/`)

| Capability | Status | What exists now | Gaps / observations |
|---|---|---|---|
| FastMCP runtime | Partial | Single `server.py`, container, service manifest | No stable browser/API adapter contract or health/readiness endpoint documented |
| Tool namespacing | Missing | Two tools named `get_costs` and `get_resources` | Target names are `cost.get_costs` and `inventory.list_resources` |
| Authentication | Missing | None | Access tokens are not verified |
| Tenant injection | Conflicting | `tenant_id` is a public tool argument | It must be derived from verified identity context and removed from caller-controlled input |
| Role enforcement | Missing | None | D2 requires checks in wrappers |
| Provider abstraction | Missing | AWS code is embedded in `server.py` | No protocol, factory, normalized models, or provider capability registry |
| AWS cost | Partial | Cost Explorer call | No pagination, validation, account fan-out, normalized response, forecast, persistence, or robust errors |
| AWS inventory | Partial | Running EC2, S3 buckets, and RDS instances | Exceptions are swallowed; only one region/session; no pagination; resource coverage and normalized model are incomplete |
| GCP provider | Missing | None | Scheduled after AWS completion |
| Azure provider | Missing | None | Scheduled after GCP completion |
| Other domains | Missing | None | FinOps, Security, SCA, Compliance, Alerts, and `auth.whoami` are absent |

### 2.4 RAG service (`rag-service/`)

| Capability | Status | What exists now | Gaps / observations |
|---|---|---|---|
| FastAPI runtime | Partial | `/health`, `/retrieve`, `/ingest`, `/history` | No auth middleware, authorization, request limits, or structured error model |
| Tenant isolation | Conflicting | Tenant-prefixed collections and tenant-filtered SQL are used | Tenant is trusted directly from `X-Tenant-Id`; this violates the security boundary |
| Embeddings | Partial | Bedrock Titan V2 codec, explicit model/allowlist/policy config, bounded calls, offline adapter tests; MiniMax runtime removed | Live regional access/policy, SDK-backed service tests, model evaluation and corpus migration remain B3.5/B8.5 |
| Chunking | Partial | Fixed 512-character chunks with overlap | No token-aware parsing, document formats, metadata policy, deduplication, or reindexing |
| Qdrant | Partial | Create/upsert/search for `rag-{tenant}` | No missing-collection behavior, collection lifecycle, payload indexes, migrations, backup, or KB/CVE collections |
| Postgres metadata/history | Partial | Document metadata and chat-message read/write | No session ownership checks, pagination contract, deletion/retention, or transaction with vector ingestion |
| Security/compliance/CVE retrieval | Missing | None | Documented endpoints and collections are not implemented |

### 2.5 Agent

| Capability | Status | What exists now | Gaps / observations |
|---|---|---|---|
| LangGraph runtime | Missing | Architecture text and UI expectation only | No graph, model client, planner, tool registry, streaming endpoint, citations, safety policy, or evaluation suite |
| Agent HTTP/SSE endpoint | Missing | nginx route points `/api/agent/` to MCP | MCP server has no `/chat` agent endpoint |
| Grounding and citations | Missing | Product requirement only | Must link tool results and RAG chunks to answer claims |
| Inference adapters and routing | Partial | Bedrock Converse adapter, typed route interface, opt-in actual Jev via Vercel evaluation API, offline API/failure tests | Authenticated LangGraph wiring, live gateway/vendor evidence and calibrated routing evaluation remain B8.2/B8.6 |

### 2.6 Data model and migrations

| Capability | Status | What exists now | Gaps / observations |
|---|---|---|---|
| Tenants | Partial | `tenants` table keyed by UUID with unique `oidc_subject` | User and tenant are conflated; no memberships or tenant-scoped role model |
| Credentials | Partial | Generic provider row with encrypted blob fields | Runtime reads filesystem JSON instead; encryption lifecycle and account/project multiplicity are undefined |
| Cost history | Partial | Daily service-level table | No provider/account dimensions, ingestion status, raw-to-normalized lineage, or migration versioning |
| Inventory | Partial | Snapshot table | Target documentation refers to a different normalized inventory model; no uniqueness/current-state strategy |
| RAG and chat | Partial | Metadata and messages | Retention, ownership, citations, and document lifecycle are incomplete |
| Security/FinOps | Missing | None | Planned migrations do not exist |
| SCA/Compliance/Alerts | Missing | None | Planned migrations do not exist |
| Migration mechanism | Conflicting | SQL files plus duplicated SQL in raw manifests and Helm templates | Multiple copies can drift; no authoritative migration runner or applied-version ledger |

### 2.7 Kubernetes, Helm, and delivery scripts

| Capability | Status | What exists now | Gaps / observations |
|---|---|---|---|
| Raw Kind manifests | Partial | Namespace, Vault, Keycloak, Postgres, MCP, app, gateway, migrations, RAG, Qdrant | Several configs are stale or incompatible; no agent/alerts/cronjobs; persistence and probes are incomplete |
| Helm chart | Conflicting | Chart, dependencies, environment values, templates | Still names the app `streamlit`; no Refine app template; duplicated old schemas/configuration |
| Keycloak | Conflicting | Realm import and deployment | Realm/client/roles/redirect URIs disagree with app configuration and product name |
| Vault | Placeholder | Dev Vault plus sidecar-shaped containers | Sidecars do not contain a complete auth/template configuration; rendered tenant files are not established |
| Secrets policy | Conflicting | Policy says no application K8s Secrets | Raw manifests still define application and tenant secrets |
| Kind setup | Partial | Builds images, installs Gateway API/Envoy, applies manifests | Network-dependent unpinned installs, weak failure handling, no port-forward/exposure validation, no smoke test |
| EKS deployment | Partial | Build/tag/push/apply script | Mutates manifests with `sed`, uses `latest`, lacks immutable releases, preflight, rollback, and post-deploy verification |
| CI/CD | Missing | None | No repeatable automated quality or release pipeline |

### 2.8 Quality, security, and operations

| Capability | Status | What exists now | Gaps / observations |
|---|---|---|---|
| Frontend scripts | Partial | `build`, `lint` (TypeScript check), dev/preview | Dependencies/lockfile absent; no unit/component/E2E tests |
| Python tests | Missing | None | No unit, contract, integration, isolation, or provider-mock tests |
| API contracts | Missing | Implicit shapes in UI and Python | No OpenAPI/client generation or shared versioned schemas |
| Observability | Missing | None | No structured logs, metrics, traces, dashboards, or alerts |
| Security controls | Placeholder | Security notes document | JWT validation, tenant-bound authorization, rate limiting, audit log, CSP/CORS policy, scanning, and threat model are absent |
| Reliability | Missing | Basic liveness/readiness on some workloads | No SLOs, retries/circuit breaking, queues, idempotency, backup/restore tests, or disaster recovery |
| Documentation | Partial | README, architecture, security stub, runbooks | Must be synchronized with implemented behavior and validated commands |

## 3. Capability matrix today

Legend: **P** partial, **—** missing. A placeholder UI without backend capability is treated as missing.

| Domain | AWS | GCP | Azure | Shared UI | Agent-ready |
|---|---:|---:|---:|---:|---:|
| Cost | P | — | — | P | — |
| Inventory | P | — | — | P | — |
| FinOps | — | — | — | — | — |
| Security | — | — | — | — | — |
| SCA | — | — | — | — | — |
| Compliance | — | — | — | — | — |
| Alerts | — | — | — | — | — |

No row is currently complete end to end because identity, authorization, API contracts, and deployment wiring are unresolved.

## 4. Execution principles

1. Deliver vertical slices that run through identity → API/tool → provider → persistence → UI → tests.
2. Finish AWS domain coverage before implementing GCP, and finish GCP parity before Azure.
3. Keep provider-neutral models and contracts from the beginning; provider-specific fields go in typed extension metadata.
4. Never treat a UI placeholder or Kubernetes manifest as a completed capability.
5. Every subphase has an executable exit gate. Work does not advance on documentation claims alone.
6. Security boundaries are established in R0 and tested continuously, not deferred to hardening.
7. Direct cloud remediation remains out of scope for v1; all provider actions are read-only.

## 5. Release roadmap overview

| Release | Goal | Depends on | Completion gate |
|---|---|---|---|
| R0 | Make the platform foundation coherent and secure | Current repository | Two-tenant Kind deployment passes build, auth, isolation, migration, and health smoke tests |
| R1 | AWS personal-beta foundation | R0 | Live/simulated onboarding, daily cost, event-driven inventory, and grounded chat work end to end on Kind and EKS |
| R2 | AWS security + weekly cockpit | R1 | Security Hub/direct checks, real-time change feed, weekly digest, and cited chat work in UI; personal AWS beta exit |
| R3 | Post-beta AWS Operations Suite | R2 | AWS SCA, compliance, evidence, anomalies, and Slack alerts work |
| R4 | GCP parity | R3 | All v1 domains meet the same provider contract and acceptance suite on GCP |
| R5 | Azure parity | R4 | All v1 domains meet the same provider contract and acceptance suite on Azure |
| R6 | Multi-cloud GA | R5 | Cross-cloud UX, scale, recovery, security, observability, and release acceptance pass |

## 6. Detailed roadmap

### R0 — Foundation repair

#### R0.1 — Freeze contracts and identity decisions

Deliverables:

- Define `UserIdentity`, `TenantContext`, `Role`, and `ProviderConnection` models.
- Implement the locked identity model: Keycloak `sub` identifies a user; server-side membership lookup resolves tenant and role. Do not use `sub` as tenant ID.
- Keep tenant switching out of scope for the beta; support one active tenant per request.
- Define a versioned HTTP adapter for browser requests and a separate internal MCP transport boundary.
- Define normalized schemas for money, time ranges, resources, findings, recommendations, vulnerabilities, controls, evidence, and alerts.
- Publish error, pagination, filtering, sorting, citation, and partial-provider-failure conventions.

Exit gate:

- Contracts are represented as executable Pydantic/OpenAPI schemas and TypeScript types.
- A tenant cannot be supplied or overridden through tool arguments, query strings, or unverified headers.

#### R0.2 — Establish a reproducible development baseline

Deliverables:

- Repair TypeScript imports and auth-provider signatures.
- Generate and commit a package lockfile; make clean install, typecheck, and production build deterministic.
- Pin Python dependencies and add formatting, linting, typing, and pytest configuration.
- Add unit-test layouts for app, MCP, RAG, and later services.
- Add a single task runner or documented command set for build, test, lint, image build, and Kind smoke.
- Add CI for build, unit tests, manifest/chart rendering, dependency scanning, and container scanning.

Exit gate:

- A clean checkout passes all local quality gates and builds every current image.
- CI repeats the same gates without cloud credentials.

#### R0.3 — Implement authentication, tenant isolation, and RBAC

Deliverables:

- Reconcile the Keycloak realm name, client IDs, roles, redirect URIs, and product branding.
- Implement shared JWKS discovery/cache, issuer/audience/expiry validation, and identity context middleware.
- Resolve tenant membership from verified claims/data; inject tenant and role into MCP/RAG/agent request context.
- Remove caller-controlled `tenant_id` tool parameters and stop trusting `X-Tenant-Id` as authority.
- Enforce `viewer`/`operator`/`admin` in UI and server wrappers.
- Add immutable audit events for login-relevant identity, tool execution, uploads, rule changes, and evidence generation without logging secrets.

Exit gate:

- Automated tests prove tenant A cannot read, search, mutate, or infer tenant B data across Postgres, Qdrant, Vault paths, and tools.
- Role-denial tests pass server-side even when UI guards are bypassed.

#### R0.4 — Rebuild migrations and core persistence

Deliverables:

- Make one ordered migration directory authoritative; remove embedded duplicate SQL from deployment templates.
- Add schema-version tracking and transactional application.
- Create tenants, users/memberships, provider connections/accounts, credential references, audit events, jobs, cost history, inventory current state/snapshots, documents, chat sessions/messages, and citations.
- Include provider/account/project/subscription dimensions in normalized tables.
- Add tenant-leading indexes and database constraints.
- Decide where Postgres row-level security supplements mandatory application predicates.

Exit gate:

- Empty-database upgrade and rollback/forward-fix procedure are tested.
- Query tests verify tenant predicates and expected indexes for all repositories.

#### R0.5 — Make secrets and deployments real

Deliverables:

- Implement Vault Kubernetes auth, policies, roles, Agent templates, renewal, and per-service least privilege.
- Remove non-bootstrap application credentials from Kubernetes Secrets.
- Create `bootstrap-tenant.sh` and `seed-vault.sh` with validation and no secret output.
- Choose one supported deployment path for each environment: raw manifests or Helm; remove or clearly deprecate the other to prevent drift.
- Replace stale `streamlit` chart naming with `app`; add agent/worker-ready topology.
- Add health, readiness, startup probes, security contexts, network policies, resource defaults, PodDisruptionBudgets where relevant, and persistent storage configuration.
- Use immutable image tags/digests and a non-mutating deploy script.

Exit gate:

- Kind starts from an empty cluster and passes a scripted smoke test.
- No application secret is stored in a normal Kubernetes Secret or printed by setup scripts.

### R1 — AWS Foundation

#### R1.1 — AWS onboarding and account model

Deliverables:

- Support many AWS accounts per tenant with connection status, account alias/ID, default region, enabled regions, and last validation time.
- Deliver the `vyom` CLI/OpenTofu onboarding path: authenticated tenant setup session, generated pinned configuration, explicit user-run apply, least-privilege read-only connector key sent once to tenant Vault, and credential validation. A GitHub App integration stores installation IDs only and can create an explicitly approved PR after the local path works.
- Preserve an upgrade path to cross-account role assumption without changing domain contracts.
- Add admin-only connection status to Settings; never return secret material to the browser.

Exit gate:

- A tenant can register, validate, disable, rotate, and remove two AWS account connections without affecting another tenant.

#### R1.2 — Provider abstraction and AWS adapter

Deliverables:

- Add provider protocol, capability declarations, normalized domain models, factory, and per-account execution context.
- Move boto3 code out of `server.py` into the AWS adapter.
- Implement bounded concurrency, SDK pagination, region discovery, retries with jitter, deadlines, rate-limit handling, and partial-account failure reporting.
- Replace swallowed exceptions with structured provider errors and telemetry.

Exit gate:

- Provider contract tests run against mocked boto3 clients.
- Adding a new provider does not require changing domain tool request/response contracts.

#### R1.3 — AWS cost

Deliverables:

- Implement `cost.get_costs` with service/account/region/tag filters, daily/monthly granularity, currency/unit normalization, and explicit inclusive/exclusive dates.
- Implement `cost.get_forecast` with documented AWS limitations.
- Add daily idempotent cost snapshot job, ingestion run tracking, backfill, and reconciliation.
- Return on-demand Cost Explorer results only with AWS freshness caveats and use persisted daily trends for dashboards; do not claim real-time billing.

Exit gate:

- Costs page reconciles to a known AWS Cost Explorer query within documented rounding/timing tolerances.
- Re-running a snapshot does not duplicate rows.

#### R1.4 — AWS inventory

Deliverables:

- Implement `inventory.list_resources`, `inventory.get_tag_coverage`, and `inventory.get_unused_resources`.
- Cover the initial AWS set: EC2, EBS, S3, RDS, Lambda, ELB/ALB/NLB, ECR, VPC/subnets/security groups/route tables, CloudTrail configuration, and Route 53 zones/records. Defer ECS discovery; Kubernetes objects use the separate B11 connector with EKS identity correlation.
- Normalize ARN/resource ID, name, service, type, account, region, tags, lifecycle state, first seen, and last seen.
- Add scheduled snapshots, current-state reconciliation, tombstoning, and on-demand refresh. Add an EventBridge → SQS → EKS-worker path for CloudTrail management events, with IRSA, DLQ, idempotency, per-tenant routing, and observable lag.

Exit gate:

- Inventory handles global and regional services, pagination, inaccessible regions, and multiple accounts.
- UI filters and counts match persisted inventory fixtures.

#### R1.5 — AWS UI foundation

Deliverables:

- Connect Overview, Costs, Inventory, and Settings to the versioned API contracts.
- Add loading, empty, partial failure, stale-data, permission, and retry states.
- Add server-driven pagination/filter/sort for inventory and accessible charts/tables for cost.
- Show provider/account scope and data freshness on every result.

Exit gate:

- A viewer can navigate the full AWS foundation workflow without direct backend knowledge.
- Browser E2E tests cover login, cost filtering, inventory filtering, and denied admin settings.

#### R1.6 — RAG and LangGraph agent foundation

Deliverables:

- Secure ingest/retrieve/history with the shared identity middleware.
- Post-beta only: add document parsing, metadata, deduplication, lifecycle, limits, and citation IDs. The personal beta has no tenant document-upload or arbitrary-ingest path.
- Implement LangGraph nodes: classify intent → plan → retrieve context → execute tools → synthesize → reflect.
- Stream responses over SSE and expose tool progress safely.
- Require grounded citations for cloud facts and KB claims; state uncertainty and partial provider failures.
- Add prompt-injection boundaries between tenant documents, tool output, and system policy.

Exit gate:

- “What did we spend on EC2 last month?” returns an AWS-grounded answer with tool/result citations.
- Agent evaluations cover correct tool selection, refusal of tenant override, citation validity, and partial failures.

#### R1.7 — AWS Foundation release gate

- Two tenants, each with at least two mocked or sandbox AWS accounts, pass the isolation suite.
- Login → live/simulated Connections → Costs → Inventory → Chat works on Kind from a clean deployment and in the dedicated EKS platform account.
- A CloudTrail fixture or live management event reaches the UI within a documented latency; duplicate and dead-letter behavior is tested.
- Snapshot jobs are observable and idempotent.
- Architecture, security, and runbooks describe implemented behavior only.

### R2 — AWS Security and FinOps

#### R2.1 — Security data model and AWS ingestion

Deliverables:

- Add findings, assets, IAM principals/relationships, exposure, encryption status, status history, and deduplication models.
- Ingest Security Hub where enabled and provide direct read-only checks for required gaps.
- For the beta, direct checks are public S3, permissive security groups, and CloudTrail health; disabled Security Hub is reported as incomplete coverage, never clean posture.
- Normalize severity, control ID, resource linkage, first/last seen, workflow state, evidence, and provider source.
- Implement `security.list_findings`, `security.get_iam_anomalies`, `security.get_public_assets`, and `security.get_encryption_status`.

Exit gate:

- Known insecure AWS fixtures produce stable normalized findings and resource drill-down links.

#### R2.2 — AWS FinOps

Deliverables:

- Add recommendation, utilization, savings estimate, reservation/commitment coverage, and acceptance-state models.
- Implement rightsizing from Compute Optimizer/CloudWatch, reservation coverage/utilization, Savings Plans-aware reporting, and idle-resource detection.
- Clearly distinguish provider recommendations from Vyom heuristics.
- Implement all four `finops.*` tools with assumptions and lookback windows.

Exit gate:

- Recommendations are reproducible from fixtures, include evidence, and never claim savings without currency and period.

#### R2.3 — Security/FinOps UI and security KB

Deliverables:

- Build production Security and FinOps pages with filters, details, severity/status views, freshness, and export.
- Create tenant-scoped security KB ingestion/retrieval and seed licensed/redistributable AWS hardening content.
- Make the agent answer exposure, remediation, rightsizing, and reservation questions with cloud-data and KB citations.
- Build a weekly digest from the daily cost history, EventBridge-fed inventory changes, and security findings. It is viewable in-app for the beta; external delivery automation is deferred.

Exit gate:

- “What public S3 buckets do I have?” and “How should I fix them?” produce distinct inventory/finding evidence and KB-backed remediation.
- The owner can review one in-app weekly digest that distinguishes live from simulated data and links every claim to source evidence.

#### R2.4 — AWS Security/FinOps release gate

- Security and FinOps acceptance suites pass for multi-account tenants.
- Stale, disabled, or unavailable source services are visible as partial coverage rather than false clean results.
- Operator/viewer permissions are enforced in both browser and backend tests.

### R3 — AWS SCA, Compliance, and Alerts

#### R3.1 — SCA ingestion and vulnerability intelligence

Deliverables:

- Accept CycloneDX and SPDX with file-size/type limits, malware-safe handling, validation, and job status.
- Normalize components to PURL; retain SBOM provenance and versions.
- Ingest ECR scan results and correlate images/components/workloads where evidence exists.
- Synchronize NVD, EPSS, and CISA KEV with source timestamps, retry/checkpoint behavior, and licensing/attribution.
- Implement `sca.get_sbom`, `sca.ingest_sbom`, `sca.list_vulnerabilities`, and admin-only `sca.sync_cve_feed`.

Exit gate:

- A fixture SBOM produces deterministic CVE, EPSS, and KEV results with source citations and no cross-tenant leakage.

#### R3.2 — AWS compliance and evidence

Deliverables:

- Add framework/control/version, assessment, evidence, mapping, exception, and bundle models.
- Implement versioned CIS AWS and SOC2 CC subset packs with explicit control-to-check mappings.
- Implement `compliance.list_frameworks`, `compliance.get_control_status`, and `compliance.generate_evidence`.
- Generate immutable, checksummed evidence bundles with manifest, timestamps, scopes, and source references.

Exit gate:

- A CIS AWS assessment shows pass/fail/not-applicable/error distinctly and can reproduce a signed/checksummed evidence bundle.

#### R3.3 — Alerts service and anomaly jobs

Deliverables:

- Build `alerts-service` with tenant-scoped rule CRUD, channel validation, events, attempts, retry/dead-letter state, and audit logs.
- Add Slack webhook delivery from Vault-rendered secrets with redaction.
- Implement cost anomaly evaluation, finding/vulnerability/control triggers, deduplication, cooldown, and rate limiting.
- Implement all `alerts.*` tools and scheduled jobs for CVE sync, anomaly evaluation, and compliance evidence.

Exit gate:

- A deterministic 3σ AWS cost fixture emits one deduplicated Slack event and records delivery status without exposing the webhook.

#### R3.4 — SCA/Compliance/Alerts UI and agent

Deliverables:

- Build SBOM upload/job status, vulnerability table and KEV badge, compliance matrix/evidence download, alert rules/events/channel test.
- Enforce role boundaries for uploads, sync, evidence generation, rule changes, and channel tests.
- Add CVE and compliance KB retrieval with cited agent answers.

Exit gate:

- AWS beta scenario passes: SBOM → KEV-highlighted vulnerabilities; CIS scan → evidence; anomaly → Slack.

### R4 — GCP parity

#### R4.1 — GCP onboarding and provider adapter

Deliverables:

- Support many GCP projects per tenant and a tenant default region/location.
- Store v1 service-account JSON in Vault; document least-privilege project/org roles and validate access.
- Implement Google SDK clients, pagination, quota projects, retries, project/location fan-out, and normalized errors.
- Pass the same provider contract suite used by AWS.

#### R4.2 — GCP Foundation

Deliverables:

- Cost: Cloud Billing export/query integration and forecast strategy with documented freshness.
- Inventory: Cloud Asset Inventory plus service enrichment for Compute, Storage, Cloud SQL, GKE, Cloud Run/Functions, load balancing, and Artifact Registry.
- Implement snapshot/backfill/current-state jobs and connect shared Costs/Inventory/Overview UI.
- Enable agent cost/inventory questions with GCP-scoped citations.

Exit gate:

- GCP foundation acceptance tests match R1 semantics, including multi-project partial failures.

#### R4.3 — GCP Security and FinOps

Deliverables:

- Security Command Center findings, IAM anomalies, public assets, and encryption posture.
- Recommender/Monitoring-driven rightsizing and idle-resource checks; commitment coverage/utilization where APIs permit.
- CIS GCP mappings and GCP hardening KB content.

Exit gate:

- Shared Security and FinOps UI/agent workflows require no provider-specific fork in their public contracts.

#### R4.4 — GCP SCA, Compliance, and Alerts

Deliverables:

- Artifact Analysis/Registry ingestion and workload correlation.
- CIS GCP assessment/evidence and SOC2 mapping reuse.
- GCP-aware anomaly, security, vulnerability, and compliance alert events.

Exit gate:

- Full domain acceptance matrix passes for GCP, including SBOM/CVE, evidence, and Slack alert flows.

#### R4.5 — GCP parity release gate

- Every v1 tool reports provider capability/support explicitly.
- AWS regression suite remains green.
- Cross-provider filters can show AWS, GCP, or both without aggregating incompatible units.

### R5 — Azure parity

#### R5.1 — Azure onboarding and provider adapter

Deliverables:

- Support one Azure tenant with multiple accessible subscriptions; track subscription scope explicitly.
- Store v1 service-principal secret in Vault; document least-privilege tenant/subscription roles and validate access.
- Implement Azure Identity/Management SDK clients, pagination, throttling/retry, subscription/region fan-out, and normalized errors.
- Pass the shared provider contract suite.

#### R5.2 — Azure Foundation

Deliverables:

- Cost Management queries/forecast with subscription, resource group, service, region, and tag dimensions.
- Azure Resource Graph inventory with enrichment for VMs/disks, Storage, SQL, AKS, Functions/App Service, load balancing, and ACR.
- Snapshot/backfill/current-state jobs and shared UI/agent integration.

Exit gate:

- Azure foundation acceptance tests match R1 semantics, including multi-subscription partial failures.

#### R5.3 — Azure Security and FinOps

Deliverables:

- Defender for Cloud findings, Entra/Azure IAM anomalies within granted scope, public assets, and encryption posture.
- Azure Advisor/Monitor rightsizing, reservation coverage/utilization, and idle-resource checks.
- CIS Azure mappings and Azure hardening KB content.

Exit gate:

- Shared Security and FinOps workflows work without Azure-only public API shapes.

#### R5.4 — Azure SCA, Compliance, and Alerts

Deliverables:

- ACR scan ingestion and workload correlation.
- CIS Azure assessment/evidence and SOC2 mapping reuse.
- Azure-aware anomaly, security, vulnerability, and compliance alerts.

Exit gate:

- Full domain acceptance matrix passes for Azure while AWS and GCP regression suites remain green.

#### R5.5 — Azure parity release gate

- A tenant with AWS accounts, GCP projects, and Azure subscriptions can query each independently and together.
- Unsupported provider/API capabilities are explicit, tested, and never represented as zero findings or zero cost.

### R6 — Multi-cloud GA and production readiness

#### R6.1 — Unified multi-cloud experience

Deliverables:

- Cross-cloud overview with provider/account/project/subscription drill-down and data freshness.
- Currency conversion policy, original-currency preservation, unit semantics, and timezone policy.
- Canonical resource links between cost, inventory, findings, recommendations, workloads, vulnerabilities, controls, and alerts.
- Saved filters/views, exports, stable deep links, and accessible responsive layouts.
- Explicit provider coverage matrix in product and API responses.

Exit gate:

- Aggregate totals are reproducible from provider-specific rows and never combine incompatible units silently.

#### R6.2 — Performance, resilience, and job architecture

Deliverables:

- Move long-running ingestion, scans, evidence, and feed sync to durable queued jobs with leases, retries, idempotency, cancellation, and dead-letter handling.
- Add concurrency/rate budgets per tenant/provider and backpressure.
- Define SLOs and capacity targets; load-test UI APIs, tool calls, Qdrant search, ingestion, and workers.
- Add Postgres/Qdrant backup, restore, point-in-time recovery where available, and disaster-recovery exercises.

Exit gate:

- Target load and provider-failure chaos tests meet SLOs without tenant starvation or duplicate side effects.
- Restore drills meet documented RPO/RTO.

#### R6.3 — Observability and operations

Deliverables:

- Structured JSON logs with request, tenant, user, job, provider, and correlation IDs; secrets and sensitive payloads redacted.
- OpenTelemetry traces/metrics across browser-facing APIs, MCP wrappers, provider SDK calls, RAG, agent nodes, jobs, and alerts.
- Dashboards and alerts for latency, errors, throttling, stale data, job lag, token use, vector health, database saturation, and delivery failures.
- Complete operational runbooks for onboarding, rotation, upgrade, rollback, backup/restore, provider outage, feed failure, and incident response.

Exit gate:

- An operator can trace a user question through agent, tools, provider calls, retrieval, and persistence using one correlation ID.

#### R6.4 — Security and privacy release review

Deliverables:

- Threat model covering tenant boundaries, OIDC, MCP/tool abuse, prompt injection, SSRF, uploads, supply chain, Vault, webhooks, and Kubernetes.
- Network policies, pod security, read-only filesystems where possible, non-root execution, egress controls, TLS, CSP/security headers, CORS, CSRF posture, and rate limits.
- Dependency/container/IaC/secret scanning and signed provenance/SBOM for released images.
- Data classification, retention/deletion, tenant export/offboarding, audit retention, and privacy documentation.
- Independent tenant-isolation and authorization review; remediate all critical/high findings.

Exit gate:

- Security checklist passes with no open critical/high release blockers.
- Tenant deletion removes or cryptographically renders inaccessible all scoped data, vectors, credentials, and backups according to policy.

#### R6.5 — Final verification and GA release

Deliverables:

- Provider sandbox E2E suites for all seven domains on AWS, GCP, and Azure.
- Contract, migration, upgrade, rollback, browser, accessibility, performance, chaos, and recovery suites.
- Versioned release artifacts, changelog, support matrix, operator guide, tenant admin guide, and known limitations.
- Production deployment with staged rollout and rollback criteria.

GA exit gate:

- All R0–R6 exit gates pass from a tagged clean checkout.
- One multi-cloud tenant and one isolation tenant complete the full acceptance journey.
- Documentation, manifests, schemas, APIs, and deployed behavior agree.

## 7. Dependency-critical path

```text
R0 contracts/identity
  → R0 auth + schema + Vault/deployment
    → R1 AWS provider abstraction
      → R1 AWS cost/inventory
        → R1 agent foundation
          → R2 AWS security/FinOps
            → R3 AWS SCA/compliance/alerts
              → R4 GCP parity
                → R5 Azure parity
                  → R6 multi-cloud GA
```

Work that can proceed in parallel after its dependency is stable:

- UI implementation can parallel backend domain work after schemas are frozen.
- Provider-mocked tests can parallel each provider adapter.
- Security KB content can parallel AWS Security ingestion after citation/licensing rules are settled.
- GCP discovery spikes may occur during AWS delivery, but production GCP implementation does not begin before the AWS beta gate.
- Azure discovery spikes may occur during GCP delivery, but production Azure implementation does not begin before GCP parity.
- Observability, audit logging, documentation, and isolation regression tests are continuous requirements even though final GA hardening is in R6.

## 8. Definition of done for every subphase

A subphase is complete only when all applicable items are true:

- Code implements the documented contract; placeholders do not count.
- Unit and contract tests cover success, validation, authorization, pagination, throttling, and partial failure.
- Tenant-isolation regression tests cover every new data store, query, collection, Vault path, job, and tool.
- UI includes loading, empty, stale, partial, denied, and error states.
- Provider calls are paginated, bounded, retried appropriately, observable, and safe to repeat.
- Schema changes have forward migration and tested upgrade behavior.
- Logs and audit records contain correlation metadata but no credentials or sensitive document content.
- Kind smoke tests pass from a clean environment.
- Architecture, security, runbook, and API documentation reflect actual behavior.

## 9. Immediate implementation queue

The numbered beta work breakdown in [`BETA_EXECUTION_PLAN.md`](BETA_EXECUTION_PLAN.md) is the authoritative near-term queue. The next work should be taken in this order:

1. R0.1: implement the locked user-versus-tenant identity model and browser API/MCP boundary.
2. R0.2: make the frontend and Python services reproducibly build and test.
3. R0.3: implement shared JWT verification and remove trusted tenant headers/tool arguments.
4. R0.4: replace the current schema with ordered core migrations.
5. R0.5: establish working Vault rendering and a clean Kind smoke test.
6. R1.1–R1.2: implement OpenTofu/CLI AWS onboarding, live/simulated connections, and the provider abstraction.
7. R1.3–R1.7: complete the AWS personal-beta vertical release, including EventBridge/SQS change ingestion.

Do not add more placeholder domain pages, advanced FinOps, SCA, formal compliance, Slack automation, or GCP/Azure cloud-provider code before these gates. The first-release milestone is a secure, reproducible, event-aware AWS cockpit with the B11 Kubernetes coverage and acceptance gate. AKS/GKE Kubernetes API coverage does not enable their cloud-provider billing/security adapters.
