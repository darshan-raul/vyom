# Vyom — Agent Guide

Tenant-isolated cloud operations cockpit for AWS, Azure, and GCP: one explainable dashboard and chat experience for spend, inventory, security exposure, software risk, and compliance, powered by RAG + LangGraph + read-only MCP tools.

**Product:** Vyom (formerly Cloud Compass; originally Cloud Cost Compass).
**Tagline:** Vyom: Grounded intelligence for the modern cloud.
**Positioning:** Tenant-isolated cloud operations. One explainable cockpit for spend, posture, and risk across AWS and Kubernetes.
**Stack:** Refine + shadcn/ui + Vite + TypeScript (UI), LangGraph/LangChain + Amazon Bedrock (agent/RAG inference), FastMCP (tools), Qdrant (RAG vectors), PostgreSQL (state), native cloud SDKs (boto3, azure-mgmt, google-cloud-*).

> Existing deployment identifiers remain historical compatibility names: K8s namespace/image prefix `cloud-cost-compass`, Keycloak realm/client IDs, and Python contract package `cloud_compass_contracts`. Product branding is **Vyom** and the planned onboarding CLI is **`vyom`**. Repository/remotes remain owner-managed (D10); infrastructure identity changes need a coordinated migration (F1.7).

---

## 1. Phase Plan

> The execution order is now provider-sequential: **AWS → GCP → Azure**. The detailed current-state inventory, subphases, dependencies, and acceptance gates are in [`docs/ROADMAP.md`](docs/ROADMAP.md). Existing `F1.x`/`F2.x`/`F3.x` IDs remain domain-backlog references.

> **Active execution tracker:** The AWS + Kubernetes first-release beta is decomposed into numbered, verifiable tasks in [`docs/BETA_EXECUTION_PLAN.md`](docs/BETA_EXECUTION_PLAN.md). B11 expands the original three-month AWS-only estimate; dates require rebaselining. Every agent MUST select work from that tracker, respect its dependencies, and update its status plus evidence when the task is verified. R0–R6 remains the post-beta roadmap.

| Phase | Scope | Status |
|---|---|---|
| R0 | Foundation repair: contracts, identity, builds, auth, schema, Vault, Kind | Pending |
| R1 | AWS Foundation: onboarding, cost, inventory, RAG chat | Pending |
| R2 | AWS Security + weekly cockpit; personal AWS beta | Pending |
| R3 | Post-beta AWS SCA + Compliance + Alerts | Pending |
| R4 | GCP full-domain parity | Pending |
| R5 | Azure full-domain parity | Pending |
| R6 | Unified multi-cloud GA and production hardening | Pending |

### Legacy domain-phase exit criteria

> These describe the final domain outcomes retained by the `F*` backlog. Delivery now occurs through R0–R6 in `docs/ROADMAP.md`, reaching each outcome for AWS first, then GCP, then Azure.

**Foundation:** Log in as tenant A, see provider spend on the Costs page; see normalized inventory on the Inventory page; ask the chat a provider-specific cost question and get a grounded answer with citations.

**Security + FinOps:** Security shows aggregated CSPM findings, drill-down works, chat answers exposure and remediation questions with KB citations, and FinOps shows rightsizing plus commitment coverage.

**SCA + Compliance + Alerts:** Upload a CycloneDX SBOM and see affected CVEs with KEV highlighted; run a provider CIS assessment and generate evidence; fire a Slack alert for a deterministic cost anomaly.

---

## 2. Decisions Locked (defaults from kickoff)

| # | Question | Decision | Alternative considered |
|---|---|---|---|
| D1 | MCP server topology | **Single FastMCP server**, namespaced tools | Per-domain or per-cloud servers (more YAML, harder ops) |
| D2 | AuthZ enforcement | **Roles checked in BOTH UI and MCP tool wrappers** (defense in depth) | UI-only, or MCP-only |
| D3 | Cloud credentials (v1) | **Static keys/secrets in Vault** (AWS access key, Azure SP secret, GCP SA JSON key) | Cross-account role assumption, Workload Identity Federation (deferred to v2) |
| D4 | MCP write-actions (v1) | **Read-only tools**, remediation as runbook text | Direct remediation writes (safety risk; deferred) |
| D5 | Compliance frameworks (v1) | **CIS AWS / Azure / GCP + SOC2 CC subset** | HIPAA, PCI, ISO 27001 (out of scope for v1) |
| D6 | Cost snapshotting | **Daily persisted** `cost_history` (cron) plus on-demand Cost Explorer queries with explicit AWS freshness caveats | Real-time only (misleading for billing) or persisted only (slow UX) |
| D7 | Multi-account per tenant | **Many AWS accounts, one Azure tenant, many GCP projects** | Strictly 1:1:1 (too restrictive) |
| D8 | Per-cloud region default | **Single default per provider per tenant, overrideable per request** | Per-resource region only (cluttered UX) |
| D9 | K8s namespace | **`cloud-cost-compass` for now** (F1.7 may rename to `cloud-compass`) | Rename immediately (disruptive; deferred) |
| D10 | Repo name | **Unchanged** — user will handle the rename | Rename to `cloud-compass` (we don't touch git remotes) |
| D11 | UI framework | **Refine + shadcn/ui** (Vite + TypeScript) | Streamlit (weak tables/streaming/RBAC), Gradio (notebook feel), Next.js (heaviest), Appsmith/Tooljet (low-code, less flexible) |
| D12 | Provider delivery order | **AWS first, then GCP, then Azure**; finish each provider release gate before production work on the next | All-cloud horizontal delivery (delays usable vertical releases) |
| D13 | First release | **AWS + Kubernetes personal-alpha cockpit**: live/simulated AWS, daily cost, inventory/change detection, Security Hub, weekly digest, grounded read-only chat, plus cluster/workload visibility, health/events, and configuration posture per D36. The original three-month estimate must be rebaselined for the expanded scope | Full Kubernetes cost/optimization/compliance/log analytics or GCP/Azure cloud-provider parity before a usable cockpit |
| D14 | Beta infrastructure | **Kind locally and EKS in a dedicated Vyom AWS account** | Docker Compose, a shared monitored/platform account, or delaying Kubernetes |
| D15 | Tenant identity | **Keycloak `sub` identifies a user; Postgres memberships resolve tenant and role**. A user may access only tenants to which the operator assigned membership, and only those tenants' cloud accounts; one active tenant is server-resolved per request in v1 | Treating `sub` as tenant ID or trusting a tenant claim/header/tool argument |
| D16 | Live change ingestion | **CloudTrail management events and Security Hub findings → EventBridge → SQS → EKS worker**, with IRSA, DLQ, idempotency, and daily reconciliation | Polling only or a public webhook ingestion endpoint |
| D17 | Cost freshness | **Daily persisted Cost Explorer history**; do not describe billing data as real-time | Event-driven or real-time cost claims |
| D18 | Initial AWS inventory | **EC2, EBS, S3, RDS, Lambda, ELB/ALB/NLB, ECR, VPC/subnets/security groups/route tables, CloudTrail configuration, and Route 53 hosted zones/records**, plus EKS cluster identity/correlation through D36's separate Kubernetes connector | ECS discovery, Kubernetes allocation/rightsizing, or packet/log analytics in the first release |
| D19 | Security source | **Security Hub when enabled**, plus direct read-only public-S3, permissive-security-group, and CloudTrail-health checks | Reimplementing AWS's entire posture engine |
| D20 | Test data | **Live AWS and clearly labelled Simulated AWS connections**; Floci and deterministic fixtures test adapters, events, anomalies, and failures | Using only a real account or treating simulated data as live |
| D21 | Connection onboarding | **Tenant-authenticated `vyom` CLI generates pinned OpenTofu configuration, validates, and supports user-run apply** | Browser secret entry or CloudFormation-first onboarding |
| D22 | GitHub integration | **GitHub App installation IDs plus short-lived installation tokens**; no tenant PATs | Storing long-lived per-tenant GitHub tokens |
| D23 | Connector secrets | **CLI submits only the newly-created least-privilege AWS read-only connector secret to tenant Vault; it never retrieves stored AWS secrets** | Backend/CLI handling broad administrator credentials |
| D24 | Beta closure | **3 active tenants; <30-minute onboarding each; ≥2 weekly returning users for 3 consecutive weeks; ≥1 actionable signal per user** | Declaring success from a personal demo or feature completion alone |
| D25 | Beta platform region | **`ap-south-1` only** for the EKS platform account; monitored AWS resources may remain global or in other regions | Multi-region platform deployment before beta evidence exists |
| D26 | Beta data lifecycle | **13 months** normalized cost/inventory/finding history; **30 days** raw event payloads; tenant-admin deletion request completed within **30 days**; platform storage in `ap-south-1`. D34 separately governs external classification processing | Indefinite retention, cross-region storage, or an undefined offboarding process |
| D27 | AI data boundary | **Reasoning and embeddings use Amazon Bedrock in `ap-south-1`**, in-region inference, account zero-retention mode, no cross-region inference, and no invocation-content logging; tenant content is never used by Vyom for model training. **D34 permits opt-in Jev intent classification through Vercel AI Gateway** with a separate data-handling gate | MiniMax, external reasoning/embedding fallback, default retention, cross-region profiles, or model training/fine-tuning on tenant content |
| D28 | Bedrock model selection | **Configurable, allowlisted in-region Bedrock chat/embedding candidates**; select the lowest-cost pair that passes zero-retention compatibility and grounded-answer evaluation | Hard-coding a model before policy/quality checks or enabling an external-provider fallback |
| D29 | Beta access domain | **`cc.darshanraul.me`** is the provisional HTTPS beta base domain; use app/auth subdomains with Route 53, ACM, and matching Keycloak redirect URIs before EKS exposure | Raw EKS endpoints, IP addresses, port forwards, or HTTP-only beta access |
| D30 | Beta user access | **Invite-only**: the operator provisions Keycloak users and tenant memberships; public self-signup is disabled | Public registration before abuse prevention, support, and account-recovery workflows exist |
| D31 | Beta chat corpus | **No tenant document uploads**. Chat is grounded only in authorized AWS/Kubernetes tool results and curated Vyom runbook text | Uploading arbitrary tenant documents before malware scanning, prompt-injection controls, retention, and deletion workflows are mature |
| D32 | Beta persistence topology | **Self-manage all platform workloads and stateful services inside EKS** (Postgres, Qdrant, Vault, Keycloak, workers). Bedrock supplies managed reasoning/embeddings; D34 adds optional external Jev classification via Vercel. Tenant EventBridge/SQS are ingestion integrations and excluded from the persistence boundary | RDS or other managed platform data services |
| D33 | Beta backup/recovery | **Velero with a dedicated encrypted S3 bucket in `ap-south-1`** for Kubernetes objects and EBS snapshots, plus native Postgres/Qdrant/Vault backups and scheduled restore drills. S3 is backup-only, not a runtime platform data service | Same-cluster-only backups, Velero-only database recovery, or RDS |
| D34 | Optional intent classifier | **Actual TypeSafe Jev through Vercel AI Gateway**, opt-in, behind a typed classifier interface. Narrow exception to D27/D32: only minimized/redacted request text for intent classification may leave AWS; never credentials, tenant/user identity, cloud tool results, or retrieved context. Failures, unknown categories, and insufficient confidence escalate to the Bedrock workflow. Authorization and calculations remain code. Gateway/provider geography, retention, and routing evaluation must pass B8.6 before activation. | Jev-like interface without actual integration or direct TypeSafe billing; owner selected actual Jev via Vercel on 2026-10-03 |
| D35 | Product identity | **Vyom**; executive tagline **“Grounded intelligence for the modern cloud.”** Owner-supplied positioning and technical pitch live in README and `docs/BRAND.md`; future CLI command is `vyom`. Preserve deployed technical identifiers until a separately verified migration | Cloud Compass / Cloud Cost Compass product names; owner requested Vyom on 2026-10-03 |
| D36 | Kubernetes coverage | **First release: EKS, AKS, GKE, and self-managed clusters through one Kubernetes connector**, read-only inventory/topology, workload/node health/events, and evidence-backed configuration posture. Server-side tenant → cluster → namespace grants; cluster-wide reads require a separate grant. Direct API collection first, optional outbound in-cluster collector for private networks. Later: existing monitoring integration, allocation without double counting, rightsizing, formal compliance/image/SBOM integration, and deeper diagnostics | Kubernetes discovery deferred from beta (superseded); treating cloud APIs as workload inventory; adding cloud billing parity solely for AKS/GKE |

> All "Alternatives considered" entries are recorded here so future maintainers (and the agent) can revisit them. If a tradeoff is overturned, update this table AND the matching tracker item.

---

## 3. Domain → MCP Tool Map

| Domain | MCP tools |
|---|---|
| Cost | `cost.get_costs`, `cost.get_forecast` |
| FinOps | `finops.get_rightsizing`, `finops.get_reservation_coverage`, `finops.get_reservation_utilization`, `finops.get_idle_resources` |
| Inventory | `inventory.list_resources`, `inventory.get_tag_coverage`, `inventory.get_unused_resources` |
| Security | `security.list_findings`, `security.get_iam_anomalies`, `security.get_public_assets`, `security.get_encryption_status` |
| SCA | `sca.list_vulnerabilities`, `sca.get_sbom`, `sca.ingest_sbom`, `sca.sync_cve_feed` |
| Compliance | `compliance.list_frameworks`, `compliance.get_control_status`, `compliance.generate_evidence` |
| Alerts | `alerts.list_rules`, `alerts.create_rule`, `alerts.delete_rule`, `alerts.list_events`, `alerts.test_channel` |
| Auth | `auth.whoami` |
| Kubernetes (planned B11) | `kubernetes.list_clusters`, `kubernetes.list_resources`, `kubernetes.get_topology`, `kubernetes.get_health`, `kubernetes.list_events`, `kubernetes.list_findings` |

---

## 4. Tracker — `F<N>.<M>` item format

> **Convention:** `F1.x` = Phase 1 item, `F2.x` = Phase 2, `F3.x` = Phase 3, `FX.x` = cross-cutting.
> **Status legend:** `[ ]` pending · `[~]` in progress · `[x]` done · `[!]` blocked · `[-]` cancelled / superseded.

### Phase 1 — Foundation

| ID | Task | Status | Owner | Notes |
|---|---|---|---|---|
| F1.1 | Rename product `Cloud Cost Compass` → `Cloud Compass` in `README.md` | `[x]` | agent | done in this commit |
| F1.2 | Rewrite `AGENTS.md` with phased plan + tracker (this file) | `[x]` | agent | done in this commit |
| F1.3 | Phase 1 SQL: `001_tenants_and_creds.sql`, `003_cost.sql`, `002_inventory.sql` | `[ ]` | agent | supersedes existing `001_initial_schema.sql`, `002_seed_tenants.sql` |
| F1.4 | Provider abstraction: `mcp-server/providers/{base,aws,gcp,azure,factory}.py` | `[ ]` | agent | `CloudProvider` protocol; AWS port from current `server.py`; implement per D12 |
| F1.5 | MCP tools `cost.*`, `inventory.*` with provider parity | `[ ]` | agent | namespaced; tenant + role injected from JWT; deliver AWS → GCP → Azure per D12 |
| F1.6a | Refine + shadcn/ui scaffold: Vite/TS/Tailwind, routing, providers, layout | `[~]` | agent | replaces Streamlit; multi-stage Docker build, nginx serve |
| F1.6b | OIDC + role-based route guards: Keycloak code flow, `viewer`/`operator`/`admin` | `[ ]` | agent | refine-auth provider; mirrors D2 (defense in depth) |
| F1.6c | Pages: Overview, Costs, Inventory, Chat, Settings (Phase 1 surface) | `[ ]` | agent | TanStack Table for inventory, Vercel AI SDK `useChat` for chat |
| F1.7 | Decide on K8s namespace rename `cloud-cost-compass` → `cloud-compass` | `[ ]` | human | D9 deferred; revisit after first multi-tenant deploy |
| F1.8 | Vault paths updated to `secret/tenants/{tid}/providers/{aws,azure,gcp}.json` | `[ ]` | agent | keep old `aws.json` path aliased during cutover |
| F1.9 | K8s manifests: namespace, Vault, Keycloak, Postgres, MCP, app, gateway, migrations, RAG, Qdrant | `[ ]` | agent | reconcile raw manifests and Helm; refresh image refs |
| F1.10 | `scripts/{setup-kind,deploy-eks}.sh` adapted for new namespace + images | `[ ]` | agent | |
| F1.11 | LangGraph agent skeleton: `classify_intent → plan → retrieve_context → execute_tools → synthesize → reflect` | `[ ]` | agent | tool registry mirrors MCP surface |
| F1.12 | End-to-end smoke: log in tenant A, see provider spend + inventory | `[ ]` | agent | deliver AWS gate first, then extend the same suite to GCP and Azure |
| F1.13 | Lock personal AWS beta scope, identity, event ingestion, and OpenTofu onboarding decisions | `[x]` | agent | D13–D23; three-month AWS beta constraints recorded |
| F1.14 | Create numbered AWS beta execution tracker and agent verification protocol | `[x]` | agent | `docs/BETA_EXECUTION_PLAN.md`; tracker governs three-month beta work |
| F1.15 | Lock AWS beta closure scorecard | `[x]` | agent | D24; owner confirmed the measurable month-three thresholds |
| F1.16 | Lock beta data lifecycle and Bedrock data boundary | `[x]` | agent | D26–D27; region/retention/no-training controls added to execution plan |
| F1.17 | Lock configurable Bedrock model-selection policy | `[x]` | agent | D28; retain evaluated Bedrock candidates without an external inference fallback |
| F1.18 | Record provisional beta HTTPS domain and access gate | `[x]` | agent | D29; DNS/ACM/Keycloak routing becomes an EKS prerequisite |
| F1.19 | Lock invite-only beta access | `[x]` | agent | D30; public self-signup is outside the beta |
| F1.20 | Lock beta chat-corpus boundary | `[x]` | agent | D31; tenant document ingestion is deferred |
| F1.21 | Lock self-managed EKS persistence topology | `[x]` | agent | D32; RDS is excluded from the beta |
| F1.22 | Lock Velero/S3 backup and native state recovery | `[x]` | agent | D33; backup storage is the documented recovery-only exception |
| F1.23 | Create target AWS beta infrastructure diagram and README preview | `[x]` | agent | Archify HTML + README PNG cover client, EKS, agent, MCP, RAG, Bedrock, events, state, and recovery |
| F1.24 | Clarify Cloud Compass product tagline | `[x]` | agent | Describe the tenant-isolated cloud operations cockpit and its explainable, read-only workflow |

### Phase 2 — Security + FinOps

| ID | Task | Status | Owner | Notes |
|---|---|---|---|---|
| F2.1 | Migrations `004_security.sql` (findings, iam_principals), `007_recommendations.sql` (partial — finops only) | `[ ]` | agent | |
| F2.2 | MCP tools `finops.*` with provider parity | `[ ]` | agent | deliver AWS → GCP → Azure per D12 |
| F2.3 | MCP tools `security.*` with provider parity | `[ ]` | agent | Security Hub → SCC → Defender for Cloud per D12 |
| F2.4 | RAG collection `kb-{tid}-security` + router `/security_kb` | `[ ]` | agent | seed with CIS Benchmarks + provider hardening |
| F2.5 | Refine pages: Security, FinOps | `[ ]` | agent | severity donut, top control IDs, drill-down (TanStack Table + Recharts) |
| F2.6 | Daily `inventory-snapshot` CronJob (K8s `09-cronjobs.yaml` shape) | `[ ]` | agent | populates `resource_inventory` |
| F2.7 | Exit criterion: Security page + FinOps page work; chat cites KB | `[ ]` | agent | |

### Phase 3 — SCA + Compliance + Alerts

| ID | Task | Status | Owner | Notes |
|---|---|---|---|---|
| F3.1 | Migrations `005_sca.sql`, `006_compliance.sql`, `007_recommendations.sql` (rest), `008_alerts.sql`, `009_seed.sql` | `[ ]` | agent | |
| F3.2 | MCP tools `sca.*` | `[ ]` | agent | ECR / ACR / GAR image scan ingestion, SBOM normalize to PURL |
| F3.3 | MCP tools `compliance.*` | `[ ]` | agent | framework packs from `compliance/*.yaml` |
| F3.4 | MCP tools `alerts.*` | `[ ]` | agent | rules CRUD, test channel, list events |
| F3.5 | `alerts-service` (FastAPI :8002) + Slack channel | `[ ]` | agent | webhook rendered by Vault Agent |
| F3.6 | CronJobs: `cve-sync` (NVD/EPSS/KEV, daily), `anomaly-eval` (hourly), `compliance-evidence` (weekly) | `[ ]` | agent | |
| F3.7 | RAG endpoints `/cve`, `/compliance_kb`; collections `cve-{tid}`, `kb-{tid}-compliance` | `[ ]` | agent | |
| F3.8 | Compliance framework packs in `compliance/`: CIS AWS / Azure / GCP, SOC2 CC | `[ ]` | agent | YAML, registered at startup |
| F3.9 | Refine pages: SCA, Compliance, Alerts | `[ ]` | agent | SBOM upload (React Dropzone), KEV badge, control matrix |
| F3.10 | Exit criterion: SBOM upload → CVE list with KEV; CIS scan → evidence bundle; anomaly → Slack | `[ ]` | agent | |

### UI Stack (locked)

- **Framework**: [Refine](https://refine.dev) (React, headless on K8s)
- **Component library**: [shadcn/ui](https://ui.shadcn.com) (Radix + Tailwind)
- **Build**: Vite + TypeScript
- **Data**: Refine data providers wrapping MCP / RAG / Alerts REST endpoints
- **Chat**: Vercel AI SDK `useChat` over SSE to the LangGraph agent
- **Auth**: Refine auth provider against Keycloak OIDC (code flow, PKCE)
- **Tables**: TanStack Table (via Refine `useTable`)
- **Charts**: Recharts
- **Serve**: nginx (multi-stage Docker build, SPA + `/api/*` reverse proxy)

> Alternatives considered: Streamlit (weak tables/streaming/RBAC), Gradio (notebook feel), Next.js (heaviest, full custom), Appsmith/Tooljet (low-code, less flexible). Refine wins on the balance of structure + flexibility for a multi-domain ops console with a serious chat surface.

### Cross-cutting

| ID | Task | Status | Owner | Notes |
|---|---|---|---|---|
| FX.1 | OpenTelemetry SDK in every service (OTLP exporter to future collector) | `[ ]` | agent | structured JSON logs with `tenant_id` field |
| FX.2 | Envelope encryption for `tenant_credentials.encrypted_blob` (DEK per row, KEK = `ENCRYPTION_KEY`) | `[ ]` | agent | upgrade from current single-key blob |
| FX.3 | Automated quality gates and `pytest` per service with mocked `CloudProvider` | `[ ]` | agent | same commands locally and in CI; no live cloud credentials required |
| FX.4 | `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/RUNBOOKS.md` | `[ ]` | agent | replaces `docs/ARCHITECTURE_PLAN.md` |
| FX.5 | `bootstrap-tenant.sh`, `seed-vault.sh` scripts | `[ ]` | agent | seed minimal tenant + creds for dev |
| FX.6 | Current-state inventory + provider-sequential completion roadmap | `[x]` | agent | `docs/ROADMAP.md`; execution order AWS → GCP → Azure |

---

## 5. Agent Invocation Tracker

> This is the running log of agent sessions working on Vyom. Historical entries retain the product name used at the time. Each entry is added by the agent when it starts and updates an item.
> **Format:** `YYYY-MM-DD HH:MM | item | status change | summary`.
>
> **Mandatory beta tracking protocol:** For every task in `docs/BETA_EXECUTION_PLAN.md`, the responsible agent MUST (1) change that task from `[ ]` to `[~]` and append a start row here before implementation, (2) leave the task `[!]` with a concrete dependency/retry condition if blocked, and (3) change it to `[x]` only after recording its test, command, deployment check, or source evidence in the task's `Evidence / update` cell and appending a completion row here. Agents MUST NOT mark a parent epic complete while an in-scope child remains unfinished, or mark a task complete from a scaffold, undocumented manual check, or unverified claim.

| When | Item | Δ | Summary |
|---|---|---|---|
| 2026-06-09 00:00 | F1.1 | `[ ] → [x]` | Renamed product to Cloud Compass in `README.md` |
| 2026-06-09 00:00 | F1.2 | `[ ] → [x]` | Rewrote `AGENTS.md` with phased plan, locked decisions, and tracker |
| 2026-06-09 00:00 | FX.4 | `[ ] → [~]` | Started architecture doc rewrite; will replace `docs/ARCHITECTURE_PLAN.md` |
| 2026-06-09 12:00 | D11 (new) | `Streamlit → Refine + shadcn/ui` | Locked UI: Refine (React, Vite, TS) + shadcn/ui (Radix + Tailwind). Reason: better tables (TanStack Table), streaming chat (Vercel AI SDK), OIDC/RBAC out of the box. Alternatives considered: Streamlit, Gradio, Next.js, Appsmith, Tooljet. |
| 2026-06-09 12:00 | F1.6 | `[ ] → split` | Split into F1.6a (scaffold), F1.6b (OIDC + guards), F1.6c (Phase 1 pages) |
| 2026-06-09 12:00 | F1.6a | `[ ] → [~]` | Scaffolding Refine + Vite + TS + Tailwind + shadcn/ui in `app/` |
| 2026-09-18 22:56 | FX.6 | `[ ] → [~]` | Started repository-backed current-state inventory and completion roadmap |
| 2026-09-18 22:56 | D12 (new) | `all-cloud horizontal → AWS → GCP → Azure` | Locked provider-sequential delivery order |
| 2026-09-18 22:56 | FX.6 | `[~] → [x]` | Added complete R0–R6 roadmap with subphases, dependencies, and exit gates |
| 2026-09-18 23:05 | FX.4 | `[~] → [~]` | Started a repository-backed interactive architecture diagram for the current implementation |
| 2026-09-18 23:11 | FX.4 | `[~] → [x]` | Delivered the source-linked Cloud Compass architecture diagram with showcase checks passing |
| 2026-09-19 18:46 | F1.13 | `[ ] → [~]` | Started recording the agreed personal AWS beta scope and architecture decisions |
| 2026-09-19 18:46 | F1.13 | `[~] → [x]` | Locked D13–D23 in the guide and synchronized roadmap/context documents |
| 2026-09-19 18:55 | F1.14 | `[ ] → [~]` | Started decomposing the AWS personal beta into verifiable numbered tasks |
| 2026-09-19 18:55 | F1.14 | `[~] → [x]` | Added the beta execution tracker, dependencies, exit scorecard, and mandatory agent update protocol |
| 2026-09-19 18:56 | F1.15 | `[ ] → [~]` | Started recording the confirmed AWS beta closure thresholds |
| 2026-09-19 18:56 | F1.15 | `[~] → [x]` | Locked D24 and marked the beta closure scorecard as confirmed |
| 2026-09-19 18:57 | D25 (new) | `region undecided → ap-south-1` | Locked the single-region EKS beta platform location |
| 2026-09-19 18:58 | F1.16 | `[ ] → [~]` | Started recording the confirmed beta retention and Bedrock inference constraints |
| 2026-09-19 18:58 | F1.16 | `[~] → [x]` | Locked D26–D27 and added enforceable lifecycle and AI data-boundary tasks |
| 2026-09-19 18:59 | F1.17 | `[ ] → [~]` | Started recording the configurable Bedrock model-selection decision |
| 2026-09-19 18:59 | F1.17 | `[~] → [x]` | Locked D28: retain evaluated Bedrock options; select only after policy and quality gates |
| 2026-09-19 19:00 | F1.18 | `[ ] → [~]` | Started recording the provisional beta-domain decision |
| 2026-09-19 19:00 | F1.18 | `[~] → [x]` | Locked D29: `cc.darshanraul.me` is the planned HTTPS beta base domain |
| 2026-09-19 19:01 | F1.19 | `[ ] → [~]` | Started recording the beta access model |
| 2026-09-19 19:01 | F1.19 | `[~] → [x]` | Locked D30: beta users are provisioned by invitation only |
| 2026-09-19 19:02 | F1.20 | `[ ] → [~]` | Started recording the beta chat-corpus boundary |
| 2026-09-19 19:02 | F1.20 | `[~] → [x]` | Locked D31: beta chat has no tenant document upload path |
| 2026-09-19 19:03 | F1.21 | `[ ] → [~]` | Started recording the EKS persistence-topology decision |
| 2026-09-19 19:03 | F1.21 | `[~] → [x]` | Locked D32: platform state stays self-managed in Kubernetes; RDS excluded |
| 2026-09-19 19:04 | F1.22 | `[ ] → [~]` | Started recording the self-managed EKS backup/recovery decision |
| 2026-09-19 19:04 | F1.22 | `[~] → [x]` | Locked D33: Velero/S3 plus native state backups and restore drills |
| 2026-09-19 19:35 | F1.23 | `[ ] → [~]` | Started the target AWS beta infrastructure diagram and README preview |
| 2026-09-19 19:35 | F1.23 | `[~] → [x]` | Added the Archify diagram HTML and a reviewed README PNG preview |
| 2026-09-19 19:39 | F1.24 | `[ ] → [~]` | Started clarifying the product tagline in README and agent guidance |
| 2026-09-19 19:39 | F1.24 | `[~] → [x]` | Updated the tagline to explain the cockpit, users' questions, and read-only MCP boundary |
| 2026-09-20 08:48 | B0.1 | `[ ] → [~]` | Started beta-document consistency review; awaiting owner confirmation of scope and identity statements |
| 2026-09-20 08:48 | B0.2 | `[ ] → [~]` | Started privacy-safe beta telemetry definition; awaiting owner measurement and retention decisions |
| 2026-09-20 08:52 | B0.1 | `[~] → [x]` | Confirmed beta scope and tenant-isolation interpretation; labelled tenant document ingest as post-beta only |
| 2026-09-20 08:52 | B0.2 | `[~] → [x]` | Added v1 privacy-safe telemetry contract with active-tenant flag, timing/failure metrics, and 30-day/13-month retention |
| 2026-09-20 08:54 | B0.3 | `[ ] → [~]` | Started defining executable Kind, EKS, simulated-AWS, and live-AWS release gates; awaiting owner choices |
| 2026-09-20 08:54 | B0.3 | `[~] → [x]` | Added Kind-first release checklist, owner-controlled EKS/live gates, immediate rollback policy, and dated evidence template |
| 2026-09-20 08:58 | B1.1 | `[ ] → [~]` | Started versioned identity, provider, event, citation, and API-error contract implementation |
| 2026-09-20 09:00 | B1.1 | `[~] → [~]` | Added v1 Python/TypeScript contracts and tests; verification awaits unavailable Python dependencies because network and Docker are unavailable |
| 2026-10-03 00:35 | B1.8 | `[ ] → [~]` | Started owner-authorized parallel inference refactor: Bedrock adapters, removal of MiniMax runtime, and actual Jev classification via Vercel AI Gateway |
| 2026-10-03 00:55 | D34 (new) | `Bedrock-only → Bedrock + optional Jev classification` | Owner selected actual TypeSafe Jev through Vercel AI Gateway; reasoning/embeddings remain on in-region Bedrock and external classification has a separate B8.6 gate |
| 2026-10-03 00:55 | B1.8 | `[~] → [x]` | Removed MiniMax runtime/configuration, added Bedrock/Jev adapters and versioned tenant vectors; 27 offline tests, Python syntax, Helm rendering, and diff checks passed; live activation/auth/migration remain pending |
| 2026-10-03 00:56 | B0.4 | `[ ] → [~]` | Started product rename to Vyom with owner-provided tagline, AWS/Kubernetes positioning, and technical pitch |
| 2026-10-03 00:57 | B0.5 | `[ ] → [~]` | Started owner-requested first-release Kubernetes scope expansion and staged tenant/namespace-safe delivery tasks |
| 2026-10-03 01:12 | B0.4 | `[~] → [x]` | Applied Vyom copy to UI and active docs; exact-copy, title/package/UI reference and SVG checks passed; historical technical IDs retained; frontend build awaits missing dependencies |
| 2026-10-03 01:12 | B0.5 | `[~] → [x]` | Aligned D13/D18/D31/D36, roadmap, architecture and release gate; defined eight pending B11 tasks; Kubernetes route included in 28 passing offline tests; original schedule requires rebaselining |
| 2026-10-03 01:28 | B1.9 | `[ ] → [~]` | Started missing-refactor repair: truthful README inventory and tested internal Kubernetes collection/normalization/topology/health/posture; production B11 dependencies remain required |
| 2026-10-03 01:42 | B1.9 | `[~] → [x]` | Implemented internal scoped Kubernetes API collection/analysis and revoked-grant history filtering; 25 offline tests and syntax/diff checks passed; corrected README inventory/auth/test claims and MCP display name; B11 production integration remains pending |

> When you (the agent) start a new task, **append a row** here with the timestamp, the `F<n>.<m>` item, the new status, and a one-line summary. When the task completes, append a second row flipping the status to `[x]`.

---

## 6. Multi-Tenancy Rules (DO NOT VIOLATE)

- Keycloak `sub` identifies the user only. The backend MUST resolve `tenant_id` and role from the server-side membership table after token verification; neither may come from a request body, query string, header, or tool argument.
- Every Postgres query in `app/`, `mcp-server/`, `rag-service/`, `alerts-service/` MUST include `WHERE tenant_id = %s`.
- Every Qdrant call MUST target a tenant-prefixed collection (`rag-{tid}`, `kb-{tid}-*`, `cve-{tid}`).
- Every Vault read for cloud creds MUST be scoped to `secret/tenants/{tenant_id}/providers/...`.
- The MCP tool server MUST inject `tenant_id` and `role` from the verified token; it MUST NOT trust `tenant_id` from the request payload.
- Role checks MUST happen in both the UI (page guard) and the MCP tool wrapper (server-side enforcement).
- Kubernetes connections MUST belong to the resolved tenant; namespace grants and cluster-wide object grants MUST be resolved server-side before collection/tool execution. No request field or model output grants access. Cluster credentials use tenant/cluster-scoped Vault paths; never collect Secret data or literal environment values.

---

## 7. Secret Hygiene

- **No Kubernetes `Secret` objects** for application secrets (cloud creds, API keys, Slack webhooks). All go through Vault Agent sidecars rendering to `emptyDir`.
- `Secret` objects ARE allowed for ephemeral bootstrap only (e.g., `00-secrets-bootstrap.yaml` feeding the Vault init job) and for TLS cert material issued by cert-manager.
- Never commit real credentials. The `placeholder` values in manifests are explicit and meant to be replaced by the Vault seed job.
- `ENCRYPTION_KEY` is a single key today; envelope encryption (FX.2) upgrades this.

---

## 8. Non-Obvious Commands

```bash
# Local Kind setup
./scripts/setup-kind.sh

# EKS deployment
./scripts/deploy-eks.sh

# Build images
docker build -t cloud-cost-compass/app:latest -f app/Dockerfile app/
docker build -t cloud-cost-compass/mcp-server:latest -f mcp-server/Dockerfile mcp-server/
docker build -t cloud-cost-compass/rag-service:latest -f rag-service/Dockerfile rag-service/

# Kind image load
kind load docker-image cloud-cost-compass/app:latest --name cloud-cost-compass
kind load docker-image cloud-cost-compass/mcp-server:latest --name cloud-cost-compass
kind load docker-image cloud-cost-compass/rag-service:latest --name cloud-cost-compass
kind load docker-image qdrant/qdrant:v1.7.4 --name cloud-cost-compass
kind load docker-image hashicorp/vault:1.16 --name cloud-cost-compass
```

## 9. Architecture (high level)

```
Browser → Envoy Gateway → Refine + shadcn/ui (8080) + LangGraph agent (SSE)
                              │
              ┌───────────────┼───────────────┐
              │               │               │
        MCP Server (8000) RAG Service (8001) Alerts Service (8002, P3)
              │               │               │
   AWS / Azure / GCP SDKs  Qdrant + Postgres  Slack webhook
                              │
                  PostgreSQL (history, inventory, findings, SBOM, compliance, alerts)
                  Vault Agent sidecar in every pod → emptyDir → /etc/secrets
```

## 10. K8s Service Inventory

| Service | Port | Phase | Notes |
|---|---|---|---|
| vault | 8200 | P1 | Dev mode, no persistence |
| keycloak | 8080 | P1 | Dev mode; realm `cloud-compass` |
| postgres | 5432 | P1 | No persistence (dev) |
| mcp-server | 8000 | P1 | FastMCP, all tools |
| streamlit | — | — | **Removed** — replaced by Refine + shadcn/ui (D11) |
| app (Refine) | 8080 | P1 | Multi-page dashboard; nginx serves static + proxies `/api/*` to backends |
| rag-service | 8001 | P1 | FastAPI |
| qdrant | 6333/6334 | P1 | gRPC/HTTP, persistent |
| alerts-service | 8002 | P3 | FastAPI; rules + channels |
| cronjobs | — | P3 | snapshot, cve-sync, anomaly-eval, compliance-evidence |

## 11. RAG

- `tenant_id` scoped chunking and retrieval.
- Beta sources: authorized AWS/Kubernetes tool results and curated Vyom runbook text only. Tenant-uploaded cost/runbook/SBOM reports and other arbitrary document ingest are post-beta work.
- Embeddings: selected in-region Bedrock embedding model under D27; collection dimension and migration are versioned with the chosen model.
- Chunking: 512-char fixed, 50-char overlap.
- Bedrock RAG collections: `rag-{tid}-v1-{embedding_spec_hash}`; legacy `rag-{tid}` requires explicit re-embedding. Planned domain collections: `kb-{tid}-security`, `kb-{tid}-compliance`, `cve-{tid}`. See `docs/INFERENCE.md`.

## 12. Quality baseline

The UI defines npm build and TypeScript-check scripts, but dependencies are not locked and no browser test suite exists yet. Python contract tests exist but still await dependencies; the RAG inference refactor has 28 passing offline tests (`scripts/test-inference.py`). The internal Kubernetes connector has 25 passing offline tests (`PYTHONPATH=mcp-server python3.11 -m unittest discover -s mcp-server/tests -v`). Service-wide lint/typecheck, dependency-backed tests, and reproducible local/CI gates remain FX.3 and roadmap R0.2 work.
