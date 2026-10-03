# Implementation plan

The [constitution](../vyom-12-week-sprint-plan.md) governs this decomposition. [TRACKER.md](TRACKER.md) alone owns status. Every item below is planned unless linked evidence proves otherwise. Dependencies are hard prerequisites for completion; independent preparation may proceed without claiming the gate passed.

## Capacity and execution

Six two-week sprints assume 20 focused hours/week. Each has 30 hours of estimated task work and 10 hours reserved for integration/failures/demonstration overrun. Estimates are planning budgets, not promises. The MCP architecture revision substitutes upstream integration work for server implementation; re-estimate S1.2–S1.3 and S2.1–S2.2 after transport/auth/capability validation. Do not assume reuse eliminates integration effort or force acceptance into the existing budget. Re-estimate after S1. If a gate slips, explicitly move later scope or dates; never silently accumulate unfinished tasks. Scope changes require updating the constitution.

Create a fresh small layout when S1.1 starts: `frontend/`, `backend/` with separate API/agent/MCP-client and direct-SDK collection modules, `tests/`, `deploy/`, `scripts/`. Add `corpus/` and migrations in S3. These are proposed paths, not pre-created scaffolds.

The [MCP integration design](MCP_INTEGRATIONS.md) supplies component responsibilities, deployment/security requirements and source-backed compatibility gates. No custom production MCP server is in scope. The UI remains S1; a CLI is a future ordinary backend API client, not a new sprint deliverable.

## Working increment

Select task → mark in progress → implement one reviewable change → run required checks → record evidence → update tracker and handoff. Keep a usable journey through each sprint. Do not begin future platform components to avoid a current integration problem.

## S1 — Smallest real agent

Planned task budget: 30 hours; sprint reserve: 10 hours.

### S1.1 — Fresh development scaffold

**Depends on:** —. **Budget:** 3 hours.

Create fresh frontend with chosen stack and FastAPI health endpoint; establish an MCP client module using an existing client SDK, not a server entrypoint. Pin compatible dependencies/lockfiles and basic CI; no future services.

**Acceptance:** Clean installs, frontend build/typecheck and backend health checks pass. Runtime contains no Vyom-owned MCP protocol server; upstream server pinning is tracked in S1.3.

### S1.2 — Evidence, MCP client and trusted context

**Depends on:** S1.1. **Budget:** 3 hours.

Define shared normalized evidence/error contracts for direct SDK and MCP results. Implement minimal client connection/negotiation/discovery/call lifecycle with operator-configured endpoint registry, server-qualified tool IDs, allowlists, typed argument and output validation, time/size limits, sanitized result projection and credential references. Choose private authenticated transport to the pinned Kubernetes server without forwarding browser credentials as Kubernetes API identity.

**Acceptance:** Reject caller/model-controlled endpoint, account/cluster/namespace authority, credential switching and unsafe tools. Evidence IDs/source/time/coverage match across both paths. Discovery/schema mismatch, auth errors and oversized output fail explicitly; no automatic trust in tool annotations.

### S1.3 — Upstream Kubernetes MCP on Kind

**Depends on:** S1.2. **Budget:** 4 hours.

Pin and deploy containers/kubernetes-mcp-server (preferred) inside Kind; configure one read-only pod capability, dedicated ServiceAccount/namespace Role and private authenticated Streamable HTTP (or justified supported transport). Specify Deployment, conditional Service, RBAC, config/secret mounts, probes/resources and sanitized logs (NetworkPolicy is optional end-of-roadmap hardening); verify actual upstream defaults and response projection. No custom protocol implementation.

**Acceptance:** Real MCP handshake/discovery/tool call matches kubectl in demo namespace. Test forbidden namespace, writes/exec, Secret access, unauthorized MCP caller and oversized results; no literal env values/raw logs reach model, UI or telemetry. RBAC and endpoint authentication verified; pinned image/config documented.

### S1.4 — Initial reasoning adapter

**Depends on:** S1.2. **Budget:** 4 hours.

Resolve endpoint/model; configure backend-only key and normalize messages, calls, errors and usage. Use ignored credential file/runtime injection.

**Acceptance:** Real tool-call round trip and malformed argument rejection pass; provider failure and missing key are sanitized; bundle/log inspection finds no credentials.

### S1.5 — Bounded graph and MCP-backed chat

**Depends on:** S1.3, S1.4. **Budget:** 5 hours.

Implement propose → host policy validation → MCP client call → sanitize/normalize → answer with one bounded tool round. Restrict exposed upstream capabilities, validate citations and show server/tool identity and evidence.

**Acceptance:** A real question traverses client and upstream server. Unsupported/unsafe tool, injected tool text, missing evidence, unauthorized scope, connection failure and timeout produce bounded explicit outcomes; no hidden switch to SDK is counted as MCP success.

### S1.6 — Direct Kubernetes evidence view

**Depends on:** S1.5. **Budget:** 3 hours.

Built only after the MCP-backed agent path works end to end. Use direct Kubernetes SDK/API projection for the deterministic resource view with a separate scoped collector identity; apply the shared evidence and authorization contract. Show time/coverage/loading/empty/error states.

**Acceptance:** Controlled workload changes appear in the direct table and independent MCP answer; source/resource identity agrees. Table remains usable with MCP down; browser never calls upstream MCP directly.

### S1.7 — Fresh Kind packaging

**Depends on:** S1.5, S1.6. **Budget:** 4 hours.

Build fresh UI/API images and one chart that pins/configures the upstream Kubernetes MCP image or chart dependency. Provide Kind values, scoped identities and private credential injection; document local access/setup/teardown. Include all deployment requirements in MCP_INTEGRATIONS.md without adding Keycloak.

**Acceptance:** Clean Kind install reaches direct resource view and real MCP chat. Deployment/Service/SA/RBAC/read-only/auth/logging checks pass, credentials remain private and production mode rejects development identity; no shared Vyom Python MCP image.

### S1.8 — S1 live gate and walkthrough

**Depends on:** S1.7. **Budget:** 4 hours.

Demonstrate unhealthy pod question, evidence, table and changed workload from clean installation; explain each boundary and a failure.

**Acceptance:** All S1 constitutional acceptance bullets recorded with exact commands/live results; offline evidence labelled separately.

## S2 — AWS and EKS evidence

Planned task budget: 30 hours; sprint reserve: 10 hours.

### S2.1 — EKS deployment and AWS MCP connectivity

**Depends on:** S1.8. **Budget:** 6 hours.

Resolve account/budget/reuse authorization; deploy same application/chart and pinned Kubernetes MCP version to ap-south-1 EKS. Set separate scoped Kubernetes identities for MCP and deterministic collection. Validate AWS-managed endpoint (or appropriate AWS-provided capability), endpoint-region/data-handling/access requirements and unattended temporary workload credentials, preferably SigV4 via supported AWS integration. Distinguish endpoint region from resource region.

**Acceptance:** Private EKS access and Kubernetes MCP auth/RBAC checks pass; real AWS MCP initialization/discovery succeeds with scoped role; expired credentials/denied calls fail. Record endpoint, offered capabilities, upstream version/SDK/proxy, quotas and retry conditions. No custom AWS MCP deployment or assumed ap-south-1 endpoint.

### S2.2 — Direct EC2 inventory and AWS MCP investigation

**Depends on:** S2.1. **Budget:** 5 hours.

Use direct AWS SDK for inventory including stopped instances, pagination, configured account/region and partial/denied states. Wire verified AWS-provided MCP capability into agent exploration; constrain any generic operation tool by allowed service/action/arguments plus IAM, not only tool name.

**Acceptance:** Direct inventory reconciles with AWS and continues during MCP outage. Live agent EC2 investigation uses AWS-managed/AWS-provided MCP; wrong-account/region and write requests fail. Missing upstream coverage leaves the gate open, not replaced by a custom wrapper or SDK-only demo.

### S2.3 — Workload and node health

**Depends on:** S2.1. **Budget:** 4 hours.

Add direct SDK readiness/restart/reason/availability projections and enable matching verified upstream MCP health capabilities. Explicitly grant node and other cluster-wide reads only when needed; keep namespace reads minimal.

**Acceptance:** Failed workload visible via both paths; node/namespace grant denial tests pass; disabling a capability never expands default RBAC/toolsets.

### S2.4 — Current resource metrics

**Depends on:** S2.3. **Budget:** 4 hours.

Use Kubernetes metrics API directly for dashboard samples; verify upstream metrics tools for chat and advertise only supported capabilities. No metrics time-series subsystem.

**Acceptance:** Contemporary kubectl top comparison passes; missing Metrics Server is unavailable, not zero; MCP coverage gap is explicit.

### S2.5 — CloudWatch EC2 metrics

**Depends on:** S2.2. **Budget:** 5 hours.

Use bounded direct SDK CPU/status-check windows for charts and verified AWS-provided MCP reads for exploratory questions. No guest memory/filesystem promise; normalize source/time/unit metadata from each path.

**Acceptance:** Window/period/unit/missing-series checks and live AWS comparison pass. Record exact permitted upstream operations and explicitly label any unsupported interactive metric capability.

### S2.6 — S2 dual-path gate and teardown rehearsal

**Depends on:** S2.2, S2.3, S2.4, S2.5. **Budget:** 6 hours.

Demonstrate direct dashboards and AWS/Kubernetes agent investigations on the same Kind/EKS release; rehearse authorized cleanup.

**Acceptance:** S2 acceptance includes both real MCP integrations, IAM/RBAC write denials, independent SDK collection under MCP failure and correct endpoint/resource-region distinction. Cost/cleanup evidence recorded.

## S3 — Bedrock, runbooks and history

Planned task budget: 30 hours; sprint reserve: 10 hours.

### S3.1 — Bedrock reasoning

**Depends on:** S2.6. **Budget:** 6 hours.

Verify in-region model/access/data handling; implement adapter and workload IAM; keep graph/tool/UI interfaces stable.

**Acceptance:** Same live journey and failure checks pass on both adapters; usage and tool messages normalize; no silent failover.

### S3.2 — Curated corpus and embeddings

**Depends on:** S3.1. **Budget:** 4 hours.

Write about five short sourced/versioned runbooks; configure separate Bedrock embedding model/dimension; operator-only bounded ingestion.

**Acceptance:** Source/section/version metadata and embeddings verified; unrelated guidance remains distinguishable from observed facts.

### S3.3 — Qdrant ingestion and retrieval

**Depends on:** S3.2. **Budget:** 4 hours.

Deploy Qdrant; workspace/model-version collections, deterministic chunk IDs, idempotent ingestion and replacement/reindex procedure.

**Acceptance:** Repeated ingest has no duplicate active chunks; model/version isolation and failed retrieval tests pass.

### S3.4 — Minimal Postgres history

**Depends on:** S3.1. **Budget:** 5 hours.

Deploy Postgres and fresh migration ledger; scoped sessions/messages/evidence/observations/errors with stable connection/resource identities.

**Acceptance:** Fresh migrations and upgrade pass; two-workspace repository tests and pod restart preserve history/citations.

### S3.5 — Graph retrieval and evaluation

**Depends on:** S3.3, S3.4. **Budget:** 4 hours.

Add bounded retrieval inside API; separate live facts, hypotheses and cited next checks; define compact evaluation cases and thresholds.

**Acceptance:** Relevant/irrelevant/stale/unavailable/injected-text cases pass agreed thresholds; all citations resolve within workspace.

### S3.6 — Direct-SDK observation schedule

**Depends on:** S3.4. **Budget:** 3 hours.

Use deterministic SDK collectors in a bounded scheduled job through ordinary libraries/APIs; idempotent keys, freshness and scoped history. Keep Postgres/Qdrant access outside MCP.

**Acceptance:** Repeated/overlapping runs do not duplicate; MCP/model outage does not stop synchronization; collector failure is not healthy data. Tests prove scopes and distinguish SDK observations from MCP evidence.

### S3.7 — S3 live gate

**Depends on:** S3.5, S3.6. **Budget:** 4 hours.

Demonstrate provider switch, workload/runbook answer, re-ingestion and restart durability.

**Acceptance:** All S3 constitutional acceptance checks and commands recorded; no general metrics-history claim.

## S4 — Investigation and cost

Planned task budget: 30 hours; sprint reserve: 10 hours.

### S4.1 — Events and relationships

**Depends on:** S3.7. **Budget:** 5 hours.

Enable bounded sanitized upstream Kubernetes MCP event/owner reads for investigation; use direct SDK reads for deterministic relationships/findings. Include Service selector conjunction and evidence-window limits.

**Acceptance:** Known fixtures and live investigation verify owner/selector behavior, bounded event projection and scope. Sensitive payloads never enter prompts/history/logs; unavailable upstream capability is explicit.

### S4.2 — Bounded multi-server investigation

**Depends on:** S4.1. **Budget:** 6 hours.

Extend graph to controlled health/event/resource/runbook sequences. Select only registered upstream connections with server-qualified tools and authorized credentials. Keep live MCP calls separate from normal retrieval/calculation APIs; enforce iteration/call/time/context budgets.

**Acceptance:** Demo investigation separates facts/hypotheses. Duplicate tool names, prompt-selected destinations, credential crossover, changing tool schemas, loops and stale/unavailable sources fail safely; no additional MCP integrations are required this sprint.

### S4.3 — Daily cost collection and questions

**Depends on:** S3.7. **Budget:** 6 hours.

Use direct Cost Explorer SDK for bounded totals/service breakdown, pagination/date/freshness and code arithmetic; persist small daily series if existing schema fits. Prefer verified AWS-provided MCP for exploratory cost reads. Agent-internal access to stored cost/calculation results is normal code, labelled distinctly from MCP.

**Acceptance:** Reconcile with equivalent live query and decimal/date/page tests. Record upstream cost coverage and provenance; missing MCP capability is not silently represented as supported. Billing never described as real-time; no custom AWS MCP wrapper.

### S4.4 — Two deterministic findings

**Depends on:** S4.1. **Budget:** 3 hours.

Implement unavailable replicas and repeated recent restarts from bounded observations; define windows/thresholds and link runbooks.

**Acceptance:** Known positive/negative/stale fixtures pass; finding has evidence/time and no unsupported root-cause claim.

### S4.5 — Optional Jev evaluation

**Depends on:** S4.2. **Budget:** 5 hours.

Implement actual intended gateway classifier behind disabled-by-default typed interface; benchmark quality/latency/failures and data boundary.

**Acceptance:** On/off evidence recorded; unknown/low confidence/failure escalates to Bedrock; activation blocked until geography/retention/minimization checks pass.

### S4.6 — S4 live gate

**Depends on:** S4.2, S4.3, S4.4, S4.5. **Budget:** 5 hours.

Demonstrate investigation and service cost explanation; record classifier activation decision.

**Acceptance:** All S4 acceptance recorded; full product journey succeeds with Jev disabled.

## S5 — Reliability baseline

Planned task budget: 30 hours; sprint reserve: 10 hours.

### S5.1 — Release and upstream compatibility automation

**Depends on:** S4.6. **Budget:** 5 hours.

Expand CI to immutable Vyom images and pinned upstream image/chart/client/proxy versions; chart validation and Kind smoke. Add upstream schema/tool-catalog regression and controlled upgrade/rollback checks.

**Acceptance:** Clean install/upgrade pass; upstream default or capability drift fails review gates rather than automatically exposing new tools. Record versions and exact smoke commands.

### S5.2 — Runtime and integration hardening

**Depends on:** S5.1. **Budget:** 6 hours.

Complete limits/retries/concurrency/job locks and security controls. Monitor MCP connection/auth/session failures, per-server/tool latency/errors/usage, direct collector freshness and credential renewal. Keep payload-free correlated audit metadata and least-privilege egress.

**Acceptance:** Dependency and token-expiry tests, restricted caller tests and recovery pass; raw prompts/secrets/tool payloads are absent from logs. Both MCP integration outages are independently observable.

### S5.3 — External backup and native restore

**Depends on:** S3.7. **Budget:** 7 hours.

Choose retention/destination/recovery objectives; consistent Postgres/Qdrant backups outside cluster; protect access; document corpus rebuild.

**Acceptance:** Restore into clean deployment verifies history, citation IDs and retrieval; measured recovery and backup access checks recorded.

### S5.4 — Answer and integration fault evaluation

**Depends on:** S5.2, S5.3. **Budget:** 6 hours.

Run grounding suite and deliberate model/AWS MCP/Kubernetes MCP/Qdrant outages; rehearse upstream and Vyom release rollback. Verify deterministic product paths continue where independent.

**Acceptance:** Agreed answer thresholds met; SDK success never masks failed MCP calls. Restored data and rollback usable; protocol/session/auth/schema errors produce explicit degraded states.

### S5.5 — S5 operational gate

**Depends on:** S5.4. **Budget:** 6 hours.

Re-run current Kind/EKS journeys and owner recovery walkthrough; consider streaming/cancellation only after required gates fit.

**Acceptance:** All S5 acceptance recorded; private alpha limitations clear; optional streaming not a release dependency.

## S6 — Identity and tenant boundary

Planned task budget: 30 hours; sprint reserve: 10 hours.

### S6.1 — Keycloak login

**Depends on:** S5.5. **Budget:** 5 hours.

Choose fresh realm/client configuration; durable Keycloak state, browser PKCE login/logout/refresh and API JWT verification.

**Acceptance:** Valid auth works; missing/expired/wrong issuer/audience tokens fail; no reuse of old identity config.

### S6.2 — Membership resolver and migration

**Depends on:** S6.1. **Budget:** 5 hours.

Add users/tenants/memberships; server resolves active tenant/role; map existing workspace to owner tenant with verified migration.

**Acceptance:** History survives migration; forged tenant inputs ignored/rejected; membership and role resolution tests pass.

### S6.3 — Grants and MCP connection isolation

**Depends on:** S6.2. **Budget:** 5 hours.

Resolve memberships/roles to tenant-owned accounts/clusters/grants. Host selects endpoint and credentials; upstream servers do not interpret Vyom tenant headers. Use separate Kubernetes MCP Deployments/ServiceAccounts per tenant grant scope initially; bind AWS temporary role/session to the authorized account. Apply identical authority to SDK collectors and UI/backend guards.

**Acceptance:** Two tenants cannot select each other’s MCP connection/role/session or broaden namespaces; write and credential-forwarding tests fail closed. No broad shared SA identity is claimed to provide tenant isolation; upstream implementation remains unmodified.

### S6.4 — Persisted and asynchronous isolation

**Depends on:** S6.3. **Budget:** 6 hours.

Apply current grants to sessions/citations/history/retrieval, any caches/checkpoints, direct collection jobs and ingest. Namespace/membership revocation invalidates MCP pools/credential bindings and updates associated RBAC before further reads; reauthorize persisted evidence.

**Acceptance:** Two-tenant ID substitution, endpoint switching, pooled-session reuse and namespace revocation tests pass across both execution paths and retained results. No call proceeds under stale grant/identity state; absent surfaces labelled unimplemented.

### S6.5 — Audit, credentials and identity recovery

**Depends on:** S6.4. **Budget:** 4 hours.

Audit grants/connection changes and denials; choose segregation, add Vault only if needed; include Keycloak state in backups.

**Acceptance:** Denial/audit checks and restored login/memberships pass; credential boundary verified without logging values.

### S6.6 — S6 isolation and exposure gate

**Depends on:** S6.5. **Budget:** 5 hours.

Run complete two-tenant matrix and recovery; disable dev resolver; configure authenticated HTTPS ingress only after gates and owner deployment authorization.

**Acceptance:** All S6 acceptance recorded. If incomplete, remain private; no public-alpha or production-readiness claim.
