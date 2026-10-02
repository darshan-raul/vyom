# Vyom — AWS + Kubernetes Beta Execution Plan

> **Tracking authority for the first-release beta.** This plan decomposes the scope in [`ROADMAP.md`](ROADMAP.md) into independently verifiable work units. The owner added Kubernetes on 2026-10-03; B11 expands the original AWS-only plan. Long-term R0–R6 remains in `ROADMAP.md`; this document governs the work required before inviting external beta users.

## 1. Tracking protocol

Every task has a stable `B<epic>.<task>` identifier. A task is not complete because code exists, a manifest applies, or a page renders. It becomes `[x]` only after its listed verification evidence is recorded in the task's **Evidence / update** cell and its dependencies are complete.

| Status | Meaning | Required tracker action |
|---|---|---|
| `[ ]` | Not started | Leave owner/evidence empty. |
| `[~]` | In progress | Set owner; append an invocation-log row in `AGENTS.md`; record an interim note only if it changes scope or exposes a blocker. |
| `[!]` | Blocked | State the specific external decision/dependency, owner, and next retry condition. Do not mark a task blocked merely because it is difficult. |
| `[-]` | Deferred/superseded | Link the decision that changed scope and identify the replacement task, if any. |
| `[x]` | Verified complete | Link or name the test, command, deployed check, and relevant code/documentation. Append a completion row in `AGENTS.md`. |

Rules:

1. Parent epics are summaries, not independently completable work. They are complete only when every non-deferred child is `[x]`.
2. Do not start a task until its `Depends on` work is verified, except for explicitly marked parallel discovery/test work.
3. Every changed interface, identity boundary, persistence path, provider call, or queue consumer requires a tenant-isolation test and a failure-path test.
4. Use simulated fixtures for deterministic tests and the personal AWS account for the live proof. The UI must distinguish them at all times.
5. Update this document and `AGENTS.md` in the same change that verifies a task. Never claim progress here without repository or deployed evidence.

## 2. Milestones and timebox

The original AWS-only estimate was 12 weeks at 20 focused hours per week. The weeks below are the historical baseline, not a committed schedule for AWS + Kubernetes. Estimate B11 and rebaseline milestone dates in B11.8 before promising the external release. A later milestone may not pull forward deferred scope.

| Milestone | Weeks | Exit result | Task range |
|---|---:|---|---|
| M0 — Foundation | 1–2 | Kind has a deterministic build/test path and secure request context | B0–B2 |
| M1 — Connected AWS | 3–4 | A live/simulated connection can be onboarded and queried safely | B3–B5 |
| M2 — Operational signals | 5–6 (rebaseline pending) | AWS signals plus Kubernetes inventory, topology, health/events, and configuration posture are visible to the owner | B6–B8, B11 |
| M3 — Personal-alpha proof | 7–8 | Owner uses EKS against the personal account and verifies the full journey | B9 |
| M4 — External beta | 9–12 | 2–3 users are onboarded; reliability and retention evidence determine next scope | B10 |

## 3. Work breakdown structure

### B0 — Governance, scope, and release controls

| ID | Task | Depends on | Verification / acceptance evidence | Status | Owner | Evidence / update |
|---|---|---|---|---|---|---|
| B0.1 | Keep `ROADMAP.md`, this plan, and locked decisions D13–D23 mutually consistent. | — | Documentation review confirms no conflicting beta scope or identity statement. | `[x]` | agent | Owner confirmed no tenant document upload/arbitrary ingest. Identity is tenant isolation: a verified user can access only the AWS accounts of the tenant to which the operator assigned membership; tenant/role are never caller-controlled. Stale post-beta document-ingest wording was labelled accordingly. |
| B0.2 | Define beta telemetry: activated tenant, successful connection, weekly active tenant, time-to-first-signal, event lag, and failed onboarding. | B0.1 | Event schema and privacy-safe metric definitions are versioned; no secrets or raw tenant payloads in telemetry. | `[x]` | agent | Owner approved an active-status flag and the privacy/retention proposal; the versioned schema and metric definitions below are the source of truth. |
| B0.3 | Define a release checklist for Kind, EKS, simulated AWS, and live personal AWS. | B0.2 | Checklist has executable commands and pass/fail evidence fields; used in B9.5 and B10.5. | `[x]` | agent | Owner confirmed Kind-first promotion, owner approval, immediate EKS rollback, a tagged dedicated resource for the sole controlled live event, and dated Markdown evidence. See `docs/RELEASE_CHECKLIST.md` and `docs/releases/README.md`. |
| B0.4 | Rename the product to Vyom and apply the owner-provided executive tagline, platform subheading, and technical pitch to the app and active documentation. | B0.1 | Product surfaces and active docs consistently use Vyom; historical decisions and deployment identity compatibility are documented; branding introduces no additional beta implementation scope. | `[x]` | agent | 2026-10-03: exact owner copy checked in README and `app/src/lib/brand.ts`; title/package/UI references and favicon XML validated; active-doc search and `git diff --check` passed. Compatibility/history policy in `docs/BRAND.md`. `npm run build` could not run: dependencies are absent (`tsc: command not found`); browser/build validation remains B2.1. |
| B0.5 | Revise first-release scope to include Kubernetes visibility, health/events, and configuration posture across EKS/AKS/GKE/self-managed clusters; define staged acceptance tasks and add Kubernetes to the typed routing vocabulary. | B0.1, B1.8 | Locked decisions, roadmap, architecture, and tracker agree on the added scope; namespace/cluster access and cost-attribution boundaries are explicit; offline classifier contract covers the Kubernetes category. | `[x]` | agent | 2026-10-03: source review aligned D13/D18/D31/D36 with `ROADMAP.md`, `ARCHITECTURE.md`, `KUBERNETES.md`, B11.1–B11.8 and release Gate E/B9.5. Checked all eight B11 tasks remain pending. Offline adapter suite passed 28 tests, including `test_kubernetes_route_is_a_planning_hint`; Python syntax/Helm rendering/diff checks passed. Scope definition and routing vocabulary only; cluster implementation/live flavor evidence and revised dates remain pending. |

#### B0 telemetry contract — v1

Telemetry is an operational, tenant-isolated measurement stream; it is not a source of cloud-infrastructure content. Each record contains only `schema_version`, pseudonymous `tenant_id` and, where necessary, `user_id`, `event_name`, `occurred_at`, `status`, bounded duration fields, connection/source kind, and a controlled error category. It must never include credentials, tokens, raw AWS event payloads, resource names/ARNs, chat prompts/responses, or provider error bodies.

| Metric | v1 definition |
|---|---|
| `tenant_active` | A tenant-level boolean status flag. It becomes true after a connection is `active` and at least one cost, inventory, finding, or event signal is successfully visible; it is cleared when the tenant is disabled or deleted. |
| Successful connection | A connection validation that authenticates using the submitted read-only connector secret, discovers its intended AWS account, and reaches the `active` state. |
| Weekly active tenant | Defined for the external-beta scorecard only: a tenant with an authenticated, successful foreground dashboard, API, or chat interaction in a rolling seven-day window. It is not collected as a decision metric during the owner-only alpha. |
| Time to first signal | Elapsed time from the authenticated CLI setup-session start to the first successful visible cost, inventory, finding, or event signal. |
| Event lag | Two durations: AWS source-event time to accepted EKS-worker time, and accepted-worker time to UI-visible time. Missing source timestamps are categorized rather than inferred. |
| Failed onboarding | A setup session ending in a terminal failed state or expiring without an active connection; record only a controlled failure category and stage. |

Raw telemetry records are retained for 30 days. Monthly aggregate metrics are retained for 13 months. Access is limited to the tenant's authorized users for tenant-level operational views and to the operator for privacy-safe beta aggregates.

### B1 — Contracts, identity, and authorization

| ID | Task | Depends on | Verification / acceptance evidence | Status | Owner | Evidence / update |
|---|---|---|---|---|---|---|
| B1.1 | Create versioned Pydantic schemas for `UserIdentity`, `TenantContext`, role, connection, provider result, event, citation, and API error envelopes. | B0.1 | Contract tests and generated/hand-maintained matching TypeScript types pass. | `[~]` | agent | Added `contracts/python/cloud_compass_contracts/v1.py`, matching `app/src/contracts/v1.ts`, and contract tests. Python syntax and `git diff --check` pass. Test execution awaits Pydantic/pytest installation: this workspace lacks them, Docker access is denied, and PyPI DNS is unavailable. |
| B1.2 | Define the browser HTTP adapter separately from internal MCP transport, including pagination, filters, freshness, partial failure, and citations. | B1.1 | OpenAPI/API contract examples cover costs, inventory, findings, connections, chat, and events. | `[ ]` | — | — |
| B1.3 | Reconcile Keycloak realm, client ID, roles, redirect URIs, localhost Kind URL, and EKS HTTPS URL. Disable public self-signup and define operator-only invite/user/membership provisioning. | B1.1 | Browser login/logout succeeds in Kind; public registration is unavailable; operator provisioning and role claims are covered by an automated test. | `[ ]` | — | — |
| B1.4 | Add JWT verification (JWKS cache, issuer, audience, expiry) shared by browser-facing services. | B1.3 | Valid, expired, wrong-issuer, and wrong-audience tests pass. | `[ ]` | — | — |
| B1.5 | Add `users`, `tenants`, and `memberships`; resolve active tenant and role from verified `sub`. | B1.4 | A user can never choose tenant/role through request fields, headers, query strings, or tool arguments. | `[ ]` | — | — |
| B1.6 | Remove trusted `X-Tenant-Id` and public `tenant_id` arguments from UI, RAG, MCP, and event paths. | B1.5 | Cross-tenant denial suite proves a forged header/argument cannot read, write, search, or infer another tenant. | `[ ]` | — | — |
| B1.7 | Enforce `viewer`/`operator`/`admin` in server wrappers and UI guards; add audit-event interface. | B1.5 | Server-side role-denial tests pass even when UI guards are bypassed; audit entries redact secrets. | `[ ]` | — | — |
| B1.8 | Refactor isolated inference adapters: remove MiniMax runtime/configuration, add Bedrock embedding/Converse adapters and opt-in actual TypeSafe Jev intent classification via Vercel AI Gateway, with model-versioned vectors and offline tests. Explicit parallel preparation authorized by owner on 2026-10-03; does not enable a public agent or waive B1/B3/B8 release gates. | B0.1; parallel adapter preparation | Mocked API contracts, classifier failure/escalation, policy denial, and tenant-separated vector namespaces pass; deployment changes contain no MiniMax configuration. | `[x]` | agent | 2026-10-03: `PYTHONDONTWRITEBYTECODE=1 python3.11 scripts/test-inference.py --sandbox-selector-poll` passed 27 tests; Python 3.11 syntax compilation and `git diff --check` passed; `helm template ai-refactor infra/k8s/charts/cloud-cost-compass --namespace cloud-cost-compass` rendered successfully (existing Postgres TLS-values warning). Runtime/config search found no MiniMax references. Adapters in `rag-service/inference/`, RAG facade in `embed/bedrock.py`, and tenant/model vector checks in `qdrant/client.py`; API sources/configuration/transition in `docs/INFERENCE.md`. Fake SDK/HTTP boundaries only: PyPI DNS blocks dependency-backed checks; no live provider/deployment or migration verified. Jev activation, tenant auth, model selection, and actual data-boundary evidence remain B1/B3/B8 gates. |
| B1.9 | Repair stale current-state documentation and implement isolated Kubernetes connector preparation: server-supplied grants, bounded read-only API lists, normalized objects, topology/health/posture and reconciliation, with offline isolation/failure tests. Parallel internal preparation in response to the owner's missing-refactor report; no public tools or deployment activation. | B0.5; parallel internal adapter/test work | Fixture integration covers namespace/cluster denials, pagination, partial coverage, secret omission, topology and tombstones; README inventory reflects actual files and auth gaps. B11 production gates remain pending. | `[x]` | agent | 2026-10-03: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=mcp-server python3.11 -m unittest discover -s mcp-server/tests -v` passed 25 tests; Python 3.11 syntax compilation and `git diff --check` passed. Tests cover wrong tenant/user/cluster before transport, scoped reads, revoked-grant history filtering, paging/limits, projection, topology, stale/partial health, posture, tombstones, HTTPS/file checks and sanitized failures. README file references/service label and pending B11 statuses checked. Internal modules in `mcp-server/connectors/kubernetes/`; MCP display name is `vyom-mcp`. No public tool registration, live cluster support, persistence/watch, onboarding, UI/agent wiring or deployment was enabled. |

### B2 — Deterministic local baseline and core persistence

| ID | Task | Depends on | Verification / acceptance evidence | Status | Owner | Evidence / update |
|---|---|---|---|---|---|---|
| B2.1 | Repair frontend imports/auth-provider conventions; lock Node dependencies and make clean install, typecheck, and production build reproducible. | B1.2 | Clean checkout passes documented install, lint/typecheck, and build commands. | `[ ]` | — | — |
| B2.2 | Pin Python dependencies; add formatter, lint, type check, pytest layout, and mocked-provider test fixtures. | B1.1 | Each Python service passes the same documented quality command without cloud credentials. | `[ ]` | — | — |
| B2.3 | Make one migration directory authoritative; add migration version ledger and transactional runner. | B1.5 | Empty-database upgrade and forward-fix/rollback procedure are tested. | `[ ]` | — | — |
| B2.4 | Create normalized persistence for provider connections, accounts, cost history, inventory current state/snapshots, findings, events, jobs, chat, citations, and audits. | B2.3 | Constraints and tenant-leading indexes are tested; repositories enforce tenant predicates. | `[ ]` | — | — |
| B2.5 | Repair Kind config, image build/load, exposure, probes, migrations, and health checks; write a one-command smoke runner. | B2.1, B2.2, B2.3 | Empty Kind cluster reaches healthy app, Keycloak, Postgres, Qdrant, Vault, and service health endpoints. | `[ ]` | — | — |
| B2.6 | Add Floci and fixture harness to local tests; make Simulated AWS a connection type, not an environment variable. | B2.2, B2.4 | Tests create normal resources, failures, a cost spike, and security findings at zero AWS cost. | `[ ]` | — | — |
| B2.7 | Implement lifecycle classification and deletion workflow: 13-month normalized history, 30-day raw event TTL, tenant-admin deletion request, and deletion audit evidence. | B2.4 | Retention/expiry tests pass; a fixture tenant is deleted or rendered inaccessible from Postgres, Qdrant, Vault, queues, and backups within the documented 30-day procedure. | `[ ]` | — | — |

### B3 — Secrets, Kubernetes, and EKS platform account

| ID | Task | Depends on | Verification / acceptance evidence | Status | Owner | Evidence / update |
|---|---|---|---|---|---|---|
| B3.1 | Implement Vault Kubernetes auth, per-service policies/roles, templates, renewal, and tenant-scoped rendered paths. | B1.5, B2.5 | Pods read only their allowed rendered secret; no application secret is a normal Kubernetes Secret or logged. | `[ ]` | — | — |
| B3.2 | Make raw manifests or Helm the supported source of truth; deprecate the other path until reconciled. | B2.5 | Selected path renders and deploys all beta services with immutable image references. | `[ ]` | — | — |
| B3.3 | Provision the dedicated platform EKS account/cluster in `ap-south-1` and baseline networking, TLS, DNS, storage, IRSA, resource limits, and network policies. Deploy Postgres, Qdrant, Vault, Keycloak, and workers as self-managed stateful Kubernetes workloads; do not introduce RDS/managed platform data services. Use `cc.darshanraul.me` as the provisional HTTPS base domain with app/auth subdomains and matching Keycloak redirect URIs. | B3.2 | EKS release checklist passes; persistent-volume failover/restart and backup/restore drills, DNS/ACM validation, HTTPS, and redirect URI tests pass; platform resources are excluded from the monitored tenant inventory. | `[ ]` | — | — |
| B3.4 | Establish deploy promotion: Kind smoke → immutable image → EKS deploy → EKS health/smoke; add rollback instructions. | B3.3 | A deliberately bad release is stopped or rolled back without data loss; commands are documented. | `[ ]` | — | — |
| B3.5 | Enforce the Bedrock AI data perimeter: `ap-south-1` only, in-region model access, zero-retention configuration, no cross-region inference, no invocation-content logging, IRSA least privilege, and deployment-policy checks. | B3.3 | Deployment fails closed when the retention/region/logging policy is absent; selected models are verified compatible with zero retention. | `[ ]` | — | — |
| B3.6 | Configure Velero with the AWS plugin, a dedicated encrypted `ap-south-1` S3 `BackupStorageLocation`, EBS `VolumeSnapshotLocation`, least-privilege IRSA, schedules, retention, and restore access. | B3.3 | Velero backup and restore of Kubernetes resources/PVCs pass in a clean namespace; bucket policy blocks public/non-TLS access. | `[ ]` | — | — |
| B3.7 | Add native consistent backup/restore jobs for Postgres, Qdrant, and Vault; store encrypted exports in the dedicated Velero S3 bucket/prefix and document ordering. | B3.6 | A point-in-time test dataset is restored into a clean cluster with expected records, vectors, and Vault data; no database consistency claim relies on a raw PVC snapshot alone. | `[ ]` | — | — |

### B4 — Tenant onboarding CLI and OpenTofu

| ID | Task | Depends on | Verification / acceptance evidence | Status | Owner | Evidence / update |
|---|---|---|---|---|---|---|
| B4.1 | Scaffold the `vyom` CLI with Keycloak device/browser login, tenant setup session, config validation, and safe diagnostics. | B1.4, B3.1 | CLI cannot act without a valid tenant-scoped session; token/secret redaction tests pass. | `[ ]` | — | — |
| B4.2 | Build a pinned OpenTofu module for dedicated read-only AWS IAM connector access and EventBridge forwarding prerequisites. | B4.1 | `tofu validate` and fixture `tofu plan` show only documented setup resources and least-privilege policy actions. | `[ ]` | — | — |
| B4.3 | Implement explicit user-run apply flow and one-time connector-secret submission directly into the tenant Vault path. | B4.2, B3.1 | Secret is never printed, returned to browser, or retrievable by the CLI after upload; validation records connection status. | `[ ]` | — | — |
| B4.4 | Add connection state machine: draft, validating, active, degraded, disabled, failed; render it in Settings. | B2.4, B4.3 | State transitions and authorization are tested; an account failure never impacts another connection. | `[ ]` | — | — |
| B4.5 | Add optional GitHub App installation discovery and a user-approved branch/PR generation path after local generation works. | B4.2 | Stores installation ID only; generated PR is scoped to the selected repo and never auto-applies. | `[ ]` | — | — |

### B5 — AWS provider and normalized data plane

| ID | Task | Depends on | Verification / acceptance evidence | Status | Owner | Evidence / update |
|---|---|---|---|---|---|---|
| B5.1 | Implement provider protocol, capability registry, factory, account execution context, structured error model, and mock contract suite. | B1.1, B2.4 | AWS and simulated adapters satisfy identical contract tests; unsupported capabilities are explicit. | `[ ]` | — | — |
| B5.2 | Implement read-only AWS authentication, account/region discovery, pagination, retries/jitter, deadlines, bounded concurrency, and partial-account failures. | B4.4, B5.1 | Mocked throttling/access-denied/region-failure tests pass and UI receives structured partial state. | `[ ]` | — | — |
| B5.3 | Implement daily Cost Explorer ingestion, idempotent history, account/service/region/tag filters, freshness metadata, and on-demand queries. | B5.2 | Known query reconciliation passes; repeated job does not duplicate data; UI labels data freshness correctly. | `[ ]` | — | — |
| B5.4 | Implement inventory discovery/normalization for EC2, EBS, S3, RDS, Lambda, ELB/ALB/NLB, and ECR. | B5.2 | Fixtures prove pagination/global-vs-regional behavior, tags, lifecycle, first/last seen, and tombstones. | `[ ]` | — | — |
| B5.5 | Implement inventory discovery/normalization for VPCs, subnets, security groups, route tables, CloudTrail config, Route 53 zones/records. | B5.2 | Fixtures prove cross-region/global scope and normalized relationships without packet/log analytics. | `[ ]` | — | — |
| B5.6 | Implement current-state reconciliation, scheduled snapshots, manual refresh, and source timestamps. | B5.3, B5.4, B5.5 | Snapshot is idempotent; removed resources tombstone correctly; refresh is authorized and observable. | `[ ]` | — | — |

### B6 — EventBridge real-time reflection

| ID | Task | Depends on | Verification / acceptance evidence | Status | Owner | Evidence / update |
|---|---|---|---|---|---|---|
| B6.1 | Define tenant/account event envelope, routing keys, idempotency key, replay policy, retention, and event-to-resource mapping. | B1.2, B2.4 | Contract tests cover duplicate, out-of-order, malformed, unknown-account, and cross-tenant events. | `[ ]` | — | — |
| B6.2 | Provision EventBridge rules/permissions and SQS main/DLQ resources through OpenTofu for CloudTrail management events and Security Hub findings. | B4.2, B6.1 | `tofu plan` and integration fixture show no public ingestion endpoint and only intended source accounts can publish. | `[ ]` | — | — |
| B6.3 | Implement EKS event worker with IRSA, long polling, validation, idempotent persistence, retry policy, DLQ metrics, and correlation IDs. | B3.3, B6.1, B6.2 | Duplicate/retry/DLQ tests pass; worker has health/readiness and no broad AWS credential. | `[ ]` | — | — |
| B6.4 | Update current inventory/security state and UI notification/feed from accepted events; preserve source event and freshness evidence. | B5.6, B6.3 | A simulated and a live CloudTrail management event appear within documented latency and remain tenant-scoped. | `[ ]` | — | — |
| B6.5 | Reconcile event stream against daily snapshots and surface gaps/lag/partial coverage. | B6.4 | Disabled trail, delayed event, and missed event fixtures become visible as coverage warnings, not false clean state. | `[ ]` | — | — |

### B7 — Security, dashboard, and weekly cockpit

| ID | Task | Depends on | Verification / acceptance evidence | Status | Owner | Evidence / update |
|---|---|---|---|---|---|---|
| B7.1 | Ingest and normalize Security Hub findings, including disabled/unavailable source state. | B5.2, B6.3 | Finding lifecycle, resource linkage, severity, deduplication, and stale/disabled coverage tests pass. | `[ ]` | — | — |
| B7.2 | Implement direct read-only checks for public S3, permissive security groups, and CloudTrail health. | B5.4, B5.5 | Positive/negative fixtures yield evidence-backed checks and never claim Security Hub-equivalent coverage. | `[ ]` | — | — |
| B7.3 | Connect Overview, Connections, Costs, Inventory, Security, and Settings to versioned APIs with loading, empty, stale, denied, and partial-failure states. | B1.2, B4.4, B5.6, B7.1 | Browser E2E covers viewer/operator/admin boundaries and all listed failure states. | `[ ]` | — | — |
| B7.4 | Build a source-linked change feed and detail view that distinguishes live from simulated data and shows event lag. | B6.4, B7.3 | User can trace a change from UI to stored event/provider evidence without tenant leakage. | `[ ]` | — | — |
| B7.5 | Build the weekly in-app digest: daily cost movement, change summary, findings, source freshness, and evidence links. | B5.3, B6.5, B7.1, B7.2 | Fixture digest is deterministic; live digest exposes unavailable/partial sources rather than silently omitting them. | `[ ]` | — | — |

### B8 — Grounded read-only chat

| ID | Task | Depends on | Verification / acceptance evidence | Status | Owner | Evidence / update |
|---|---|---|---|---|---|---|
| B8.1 | Secure chat history and curated-runbook retrieval with identity middleware and tenant-scoped Qdrant/Postgres access. Do not expose a tenant document-upload or arbitrary-ingest path in beta. | B1.6, B2.4 | Cross-tenant retrieval/history tests pass; API/UI tests prove tenant document uploads and arbitrary ingest are unavailable. | `[ ]` | — | — |
| B8.2 | Implement LangGraph read-only flow: classify → plan → retrieve → execute allowed tools → synthesize → reflect. | B5.1, B7.1, B8.1 | Tool registry excludes writes and tenant override; tool selection tests pass. | `[ ]` | — | — |
| B8.3 | Add SSE chat API and UI tool progress, source citations, uncertainty/partial-failure handling, and prompt-injection boundaries for tool results and curated runbooks. | B1.2, B8.2 | E2E asks cost/change/security questions; each factual answer cites a tool/result or curated-runbook source. | `[ ]` | — | — |
| B8.4 | Add evaluation set for cost, inventory, changes, Security Hub/direct checks, simulation label, tenant override refusal, and partial failures. | B8.3 | Evaluation is repeatable in CI with fixtures; regressions block release. | `[ ]` | — | — |
| B8.5 | Activate and evaluate the Bedrock chat/embedding adapters prepared in B1.8; retain in-region candidate options, select the lowest-cost pair compatible with B3.5 that passes grounded-answer evaluations, and migrate/reindex the live corpus into model-versioned collections safely. | B1.8, B3.5, B8.1 | SDK-backed/live adapter checks prove in-region Bedrock invocation, no prompt/response logging, correct vector dimension, safe reindexing with no tenant mixing, and recorded policy/quality/cost selection evidence. | `[ ]` | — | — |
| B8.6 | Activate and evaluate optional actual TypeSafe Jev intent routing through Vercel AI Gateway in LangGraph after authenticated tenant context exists; verify gateway/provider processing locations/retention and Vault-rendered gateway API key, validate input minimization, document the external prompt-classification boundary, and calibrate escalation thresholds. | B1.8, B1.6, B8.2 | Live credential smoke, labelled routing evaluation, outage/escalation E2E, tenant-boundary tests, and gateway/provider data-handling evidence pass; turning Jev off preserves the Bedrock workflow. | `[ ]` | — | — |

### B9 — Personal-account alpha

| ID | Task | Depends on | Verification / acceptance evidence | Status | Owner | Evidence / update |
|---|---|---|---|---|---|---|
| B9.1 | Connect the personal AWS account through the CLI/OpenTofu flow and verify least privilege. | B3.4, B4.4, B6.2 | Connection reaches `active`; access-policy validation shows only beta read actions; no secrets are captured in logs. | `[ ]` | — | — |
| B9.2 | Enable/verify CloudTrail and Security Hub source coverage; test a controlled management change. | B6.4, B7.2 | Change reaches EKS/UI within documented latency; disabled coverage is displayed accurately. | `[ ]` | — | — |
| B9.3 | Verify live daily Cost Explorer, inventory snapshots, findings, weekly digest, and cited chat against the personal account. | B5.6, B7.5, B8.4 | Owner completes a written weekly-use script and records discrepancies/fixes. | `[ ]` | — | — |
| B9.4 | Run security, Velero/PVC and native-state backup/restore, credential rotation/revocation, incident, and rollback drills for beta services. | B3.4, B3.6, B3.7, B9.1 | Runbooks have dated drill evidence; a revoked connector fails closed and is visible as degraded. | `[ ]` | — | — |
| B9.5 | Execute the M3 release checklist from a clean Kind deployment and EKS release, including Kubernetes first-release coverage. | B0.3, B9.1–B9.4, B11.8 | All required AWS and Kubernetes checks pass; unresolved items are explicitly deferred, not waived. | `[ ]` | — | — |

### B10 — External beta and closure decision

| ID | Task | Depends on | Verification / acceptance evidence | Status | Owner | Evidence / update |
|---|---|---|---|---|---|---|
| B10.1 | Recruit 2–3 trusted AWS design partners and document consent, support channel, data boundaries, and rollback/offboarding path. Provision each through the invite-only Keycloak/membership flow. | B9.5 | Each participant has an assigned tenant, invite, and supported contact/exit path; public self-signup remains unavailable. | `[ ]` | — | — |
| B10.2 | Onboard each partner through the CLI/OpenTofu connection path; measure time-to-first-signal and every failure point. | B10.1 | At least three tenants connect an account in under 30 minutes, or failures drive a documented remediation task. | `[ ]` | — | — |
| B10.3 | Run three weekly-use cycles; capture activation, weekly active tenants, evidence-link usage, and actionable signals. | B10.2, B7.5, B8.3 | At least two users return weekly for three consecutive weeks and each identifies an actionable change, cost movement, or finding. | `[ ]` | — | — |
| B10.4 | Resolve P0/P1 beta defects and reliability issues; freeze new domains and nonessential integrations. | B10.3 | Triage log has no unaccepted P0/P1 issue; regression suite stays green. | `[ ]` | — | — |
| B10.5 | Make the month-three closure decision: continue AWS hardening, expand AWS post-beta scope, or begin GCP discovery. | B10.4 | Written decision references success metrics, operating cost, reliability, user feedback, and unresolved risks. | `[ ]` | — | — |

### B11 — Kubernetes first-release coverage

The Kubernetes API has its own connector; AKS/GKE visibility does not enable Azure/GCP billing or full cloud-provider parity. These tasks are pending implementation. See [`KUBERNETES.md`](KUBERNETES.md) for collection boundaries and later governance/optimization/operations stages.

| ID | Task | Depends on | Verification / acceptance evidence | Status | Owner | Evidence / update |
|---|---|---|---|---|---|---|
| B11.1 | Define cluster connections, flavor/capabilities, namespace and separate cluster-wide grants, normalized objects/health/events/findings/relationships, and tenant-leading persistence contracts. | B1.1, B1.5, B2.4 | Contract/isolation tests cover tenant + cluster + UID keys, namespace versus cluster scope, unknown cloud links, freshness, and D26 lifecycle classification. | `[ ]` | — | — |
| B11.2 | Add `vyom` CLI read-only cluster onboarding with dedicated RBAC, authenticated TLS, tenant/cluster Vault credentials, grant validation, rotation/revocation, and connection status. Reject unsafe kubeconfig exec hooks and unauthorized network targets. | B11.1, B3.1, B4.1 | Denial tests exclude Secret reads, exec/attach, proxy and writes; credentials never reach browser/logs/Jev; invalid certificates, revoked access, and namespace/cluster grant violations fail closed. | `[ ]` | — | — |
| B11.3 | Implement optional in-cluster outbound collection for unreachable private clusters: authenticated enrollment, identity renewal, tenant/cluster binding, replay protection, bounded observations, health and reconciliation. | B11.1, B11.2, B2.5 | Wrong-tenant/forged/expired/duplicate messages and collector outages are tested; recovery reconciles gaps; private credentials stay within the authorized connector boundary. | `[ ]` | — | — |
| B11.4 | Implement Kubernetes API list/watch + reconciliation for the first-release object set, enforcing namespace and cluster-wide permissions before collection. | B11.1, B11.2 | Kind fixtures cover pagination, reconnects, duplicates/out-of-order observations, deletion, missing APIs and denied reads. No broad read followed by client-side namespace filtering; normalized fields omit secrets and literal environment values. | `[ ]` | — | — |
| B11.5 | Build topology and evidence-based cloud correlation: workload/pod/node/cloud instance, service/load balancer, PVC/PV/volume, and namespace/team/app ownership. | B11.4, B5.4, B5.5 | Cross-tenant joins are denied; missing Azure/GCP/self-managed links stay unknown; unsupported/partial relationships are visible. Vyom's platform cluster is excluded unless explicitly onboarded. | `[ ]` | — | — |
| B11.6 | Add workload/node health, bounded recent events, and configuration posture checks for privileged/host access, risky service accounts, broad RBAC, public exposure and isolation evidence. | B11.4 | Positive/negative/denied/stale fixtures show evidence and coverage. Partial reads never produce a clean posture claim; health does not imply historical usage, log analytics or a full CIS assessment. | `[ ]` | — | — |
| B11.7 | Expose authorized `kubernetes.*` MCP tools and cluster UI, topology/health/posture views, cited LangGraph diagnostics and optional Jev routing. | B11.5, B11.6, B1.2, B1.7, B8.3 | E2E tests enforce role + tenant + cluster + namespace grants, failure states and evidence citations. Neither classifier nor tool arguments can grant access; Jev-disabled/outage paths preserve planning. | `[ ]` | — | — |
| B11.8 | Verify the Kubernetes first-release gate across EKS/AKS/GKE/self-managed capabilities and private-collector recovery; estimate remaining work and rebaseline milestone dates. | B11.3, B11.7, B2.7 | Kind conformance plus flavor-specific live evidence record supported API versions, access limitations, topology/health/posture, credential revocation and deletion. Support claims require that flavor's evidence; documented effort/dependencies produce a revised schedule. | `[ ]` | — | — |

## 4. Dependency guardrails

```text
B0 governance
  → B1 contracts + identity
    → B2 reproducible baseline + persistence
      → B3 Kind/EKS/Vault platform
        → B4 CLI + OpenTofu onboarding
          → B5 AWS provider + daily data
            → B6 EventBridge/SQS reflection
              → B7 cockpit + digest ─┐
              → B8 grounded chat ───┼→ B9 personal alpha → B10 external beta
                                    ┘
```

Permitted parallel work: B0.2/B0.3 after B0.1; owner-requested B1.8/B1.9 internal adapter/test preparation; B2.1/B2.2; B5.3–B5.5 after B5.2; B7.1/B7.2 after their data dependencies; B8.1 while the AWS adapter is built; B11 tasks alongside AWS work once their own dependencies pass. B11.8 is required before B9.5. No GCP/Azure cloud-provider parity, SCA, formal compliance, advanced FinOps, Slack automation, or write-remediation work may enter this plan before B10.5. Common Kubernetes API coverage of AKS/GKE is the explicit B11 exception.

## 5. Beta closure scorecard (locked)

The project owner confirmed these month-three thresholds. B10.5 cannot declare the beta closed without evidence for every applicable measure or an explicit documented decision to change the target.

| Measure | Target | Evidence source |
|---|---:|---|
| Active tenants | ≥3 | Tenant activation records |
| Onboarding time | <30 minutes per tenant | CLI/setup telemetry and operator notes |
| Retention | ≥2 users weekly for 3 consecutive weeks | Privacy-safe activity metrics |
| Operational value | ≥1 actionable signal per user | Weekly review notes linked to source evidence |
| Safety | 0 accepted cross-tenant or write-action defects | Isolation suite, audit review, release checklist |
| Reliability | No unresolved P0/P1 beta issue | Triage log and regression suite |
