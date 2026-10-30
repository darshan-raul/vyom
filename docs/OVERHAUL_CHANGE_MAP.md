# Repository overhaul change map

Reviewed 29 October 2026 against the accepted [continuous operations design](CONTINUOUS_OPERATIONS.md). This is the implementation checklist for existing R tasks, not a second feature backlog. Boxes remain unchecked until implementation and the named evidence exist. P13 completes the review only.

Scope: current tracked/untracked application source, tests, frontend, deployment, scripts, CI, planning and reference assets. Existing staged deletions and modifications were inspected, not reverted. Ignored credentials, virtual environments, build outputs and Git history were excluded; binary artwork was classified by usage rather than re-reviewed visually. No runtime test suite, live cluster or dependency vulnerability audit was run for this documentation review.

## Priority findings

1. **P0, R2:** `evidence.resource_id()` uses cluster/namespace/kind/name, not UID. That is suitable for the existing transient lookup but unsafe as durable object identity. Name reuse must not transfer old relationships, findings or episodes. Introduce UID-backed scoped identity and explicit unresolved MCP references; preserve old citations through an adapter/version boundary.
2. **P0, R3:** `GET /api/kubernetes/pods` calls the collector per request; `usePods()` polls it. There is no autonomous observation while the UI is closed. Separate scheduled collection from stored inventory reads before claiming monitoring.
3. **P0, R3/R4:** Kubernetes Table results expose readiness/status/restarts but omit the workload spec, owner graph, container termination, probes and scheduling evidence needed for diagnosis. Add typed, safe projections and separately justified provider permissions; increasing the model's tool budget alone cannot solve this.
4. **P0, R4a:** No durable issue, episode, job, lease, conversation or recovery state exists. Single-request LangGraph execution is not a background triage engine. Database-backed idempotency and recovery must precede automatic triggers.
5. **P0, cross-cutting:** The active roadmap leaves former S5/S6 recovery and identity work without a new task. Private fixed-operator mode is acceptable for the local loop, but no multi-user/remote exposure is acceptable until verified identity, grants, revocation and recovery gates are explicitly scheduled.
6. **P1, R1 — corrected in 2026-10-29-05:** Active constitution, agreement, architecture, plan and verification are consolidated. `check-docs.py` now validates active R dependencies/statuses/evidence with negative regression cases; historical results remain separately labelled.

## Backend and domain checklist

| Mark / owner | Files or area | Required change and acceptance |
|---|---|---|
| CHANGE R2 | `backend/src/vyom/evidence.py`, `tests/test_evidence.py`, `test_pod_collector.py` | [x] Add durable resource/observation identities, scoped references and provenance versions; keep complete/zero/partial/denied/missing distinctions. Test UID recreation, source ambiguity, stale-and-partial coverage and citation resolution after restart. Do not overwrite evidence when latest state changes. ([2026-10-29-09](sessions/2026-10-29-09.md), [2026-10-30-01](sessions/2026-10-30-01.md)) |
| CHANGE R2/R3 | `context.py`, `mcp_client/registry.py` | [ ] Separate workspace/connection authority from Kubernetes-only location fields. Support cluster-scoped resources without fake namespaces, then multiple explicitly configured scopes. No browser-defined authority or generic provider framework. |
| ADD R2 | Postgres persistence and migrations, `backend/pyproject.toml`, `backend/uv.lock` | [x] R2.1 done in [2026-10-29-09](sessions/2026-10-29-09.md), R2.2 done in [2026-10-30-01](sessions/2026-10-30-01.md), R2.3 done in [2026-10-30-02](sessions/2026-10-30-02.md): `inventory/` schema, migration runner, store, config, database connection manager, collector/API persistence, citation resolution, retention pruning, chart packaging and Kind restore tests. Resources, relationships, collection_runs and observations; workspace-scoped uniqueness/FKs and query contracts, transactions, bounded retention, migration/restore tests. Add dependencies only with implementation; no unused security/job tables. |
| CHANGE R3 | `collectors/kubernetes.py` | [ ] Keep native direct collection and independent credentials; add typed workload/owner/status projections, field allowlists, bounded pagination and configurable freshness. Successful complete scans alone may establish absence. Test failed later pages, deletion/recreation, expired credentials and a closed browser. |
| ADD R3 | Collection scheduler (absent) | [ ] Persist scheduling/progress, bounded overlap prevention and backoff; classify collection health independently from resource health. No duplicate collection per API worker and no refresh storm from many browsers. |
| CHANGE R3/R4 | `api/app.py` | [ ] Add stored inventory/list/detail/evidence contracts with server-side filters/pagination and scope checks. Preserve current routes during migration. Split route modules when real endpoints justify it; expose liveness separately from dependency readiness. |
| CHANGE R4 | `agent/graph.py` | [ ] Replace mandatory fresh-tool-per-answer behavior with inventory context plus selective verification. Implement one explicit workload skill, bounded branches and typed conclusions/hypotheses. Keep strict evidence validation; do not interpret citation presence as proof that every causal claim is supported. |
| RETAIN + EXTEND R4a | `agent/model.py`, `credentials.py` | [ ] Reuse normalized failures, private credentials and export controls. Add aggregate run budgets/admission policy; missing token usage must not count as zero. Provider replacement is separate from investigation workflow. Bedrock is deferred, not silently substituted. |
| RETAIN + EXTEND R4 | `mcp_client/host.py`, `tools.py`, `kubernetes.py`, `registry.py` | [ ] Retain reviewed schema/allowlist, credential binding, response bounds and sanitization. Review each added evidence tool. Current text table has no UID or continuation proof; do not use it for authoritative deletion or identity reconciliation. |
| ADD R4a | Change detector, issues/episodes, job runner | [ ] Compare meaningful normalized fields after a baseline; group exact relationships first. Uniqueness, leases, cooldowns, retry caps, stale-result guards and observed recovery. Test flapping, restarts, duplicate polls, simultaneous workers and recovery during triage. |
| CHANGE R4/R4a | `/api/chat`, `ChatRequest`, `ChatResult` | [ ] Add server-resolved investigation/issue references and bounded persisted turns. Async start/status/results for background jobs; conversation remains distinct from evidence. Requests cannot select credentials or grant scope. Keep compatibility or explicitly version old response contracts. |
| ADD R5/R8 | Security engine/rules/findings (absent) | [ ] Deterministic versioned rules, policy parameters, categories, evidence and useful remediation; test false positives, unknown fields, stale inventory and finding resolution. A risky configuration is not confirmed exploitation. |
| DEFER until R6/R7 | AWS collectors/connectivity | [ ] Implement native inventory and bounded path investigation only after Kubernetes gates. Use account/region/native identity, configuration-vs-traffic evidence and fixtures; real sandbox needs specific provisioning authorization. |
| RETAIN + EXTEND consuming task | `telemetry.py` | [ ] Preserve payload-free bounded metrics/logs/traces; add aggregate collection freshness, queue depth/age, dropped/retried jobs and investigation outcomes. No resource/issue IDs as metric labels or prompts/tool bodies in logs. Monitoring must reveal its own blind spots without requiring an LLM. |
| RETAIN R1/R3 | `token_refresher.py`, credential tests | [ ] Keep separate short-lived collector identity and rotation checks; extend only for actual new collector grants. Do not merge observer, agent and collector authority. |

## Frontend checklist

| Mark / owner | Files or area | Required change and acceptance |
|---|---|---|
| CHANGE R3/R4a | `pages/today.tsx`, `App.tsx`, `components/vyom/sidebar.tsx` | [ ] Overview becomes active issues, changes, freshness and investigation progress from real APIs. Rename internal Today component when touching its feature, preserve `/`. No sample counts or disabled roadmap links. |
| CHANGE R3 | `pages/kubernetes.tsx`, `lib/pods.ts` | [ ] Inventory query/filter/pagination and resource-detail links. API reads persisted state; UI polling refreshes the view, not provider collection. Show stale, denied, unavailable and truly empty separately. |
| CHANGE R3/R4 | `dataProvider.ts`, `lib/agent.ts` | [ ] Implement read list/detail methods as needed, typed API contracts and meaningful non-2xx/error states. Current handwritten types are Kubernetes-only; introduce generated types or contract tests to prevent drift. |
| CHANGE R4a | `ask-vyom.tsx`, `answer.tsx`, `lib/agent.ts` | [ ] Preserve natural-language entry; add issue-scoped turns, persistent evidence links and job progress. Current React state holds one question/result only. Test route navigation/reload and failed runs without losing history. |
| ADD R4a/R5 | Issue detail and Security views | [ ] Timeline, attempts, evidence, acknowledgement/resolution reasons and finding detail. Internal issue writes do not authorize infrastructure mutations. No claim that agent completion implies recovery. |
| RETAIN | `components/ui/*`, status components, `index.css`, fonts/assets | Keep visual system and canonical logo. Verify keyboard/focus, contrast, narrow screens and long evidence in the new surfaces; no broad redesign. |
| REVIEW R4a | `pipeline-strip.tsx` | [ ] Replace the synchronous request-path emphasis with real investigation steps where needed; don't display configuration as health. |

## Deployment, local workflow and CI checklist

| Mark / owner | Files or area | Required change and acceptance |
|---|---|---|
| VERIFY R1 | `scripts/vyom-up.sh`, `observability-up.sh`, `vyom-check.sh`, chart values | [x] Fresh none/metrics gates passed in [2026-10-29-06](sessions/2026-10-29-06.md); the optional full-profile live regression was not run. Run fresh none/metrics profiles and explicit full-profile regression. Check absent trace exporter and optional stores, CRD preflight, invalid profile refusal and reported SKIPs. Profile rendering alone is not installation proof. |
| CHANGE R2 | `deploy/chart/vyom/templates/*`, `values.yaml`, Dockerfiles | [x] Add private Postgres config/credentials/storage and controlled migration execution, readiness and recovery instructions. Test upgrade and rollback compatibility; never run destructive migrations on every API startup. ([2026-10-30-02](sessions/2026-10-30-02.md)) |
| CHANGE R3/R4 | `templates/identities.yaml`, MCP config, operator config | [ ] Current two read Roles permit only pod `list` in one namespace. Add narrowly scoped workload reads and cluster roles only where needed; prove denied Secret values, exec/writes and unauthorized scopes. Metadata-only collection is an application projection, not a Kubernetes RBAC field restriction. |
| CHANGE R4a | Chart/backend entrypoints | [ ] Run leased jobs independently of HTTP request lifetime with graceful shutdown and bounded concurrency. Choose a small worker process using the same code/image; no new broker required. Test worker loss/restart. |
| RETAIN + REVIEW R4a | `frontend/nginx.conf`, health probes | [ ] Preserve private same-origin routing; async job polling must not depend on the existing 90-second synchronous proxy window. Keep application access localhost/internal until identity gate. |
| CHANGE R1 | `scripts/dev-up.sh`, `vyom-up.sh`, `vyom-forward.sh`, live probes | [x] Every cluster script refuses a non-`kind-*` context ([2026-10-29-08](sessions/2026-10-29-08.md)). Align profile/context instructions and remove obsolete S-sprint requirement wording. Explicit target-context validation before mutation; never select the user's current cluster implicitly. Review custom-context/create-cluster behavior before supporting new cluster enrollment. |
| RETAIN + CLASSIFY R1 | `observability-check.sh`, `s18-gate.sh`, `s18_gate.py`, `deploy/observability/*` | Historical full-stack gates remain optional integration tests. Separate application/metrics acceptance from Loki/Tempo outage gates; preserve pinned vendor config and security tests. |
| ADD R4 | `labs/kubernetes/` (absent), existing `deploy/kind/demo.yaml` | [ ] Ten named diagnostic labs with symptom/evidence/diagnosis/cleanup. Clearly separate operator lab mutations from product's read-only identities; don't treat the single demo manifest as the regression suite. |
| CHANGE R1 onward | `.github/workflows/ci.yml` | [ ] Docs checks, checker tests and shell syntax were added in R1; backend tests now run against a Postgres service container. Still to add: chart/profile render, then Postgres integration and lab/job gates as features land. No secret-bearing live model tests on untrusted PRs. |
| RETAIN + REVIEW consuming task | `.gitignore`, `.dockerignore`, image/chart locks, package locks | Preserve credential/build exclusions and reproducible pins. Review build contexts and generated diagram outputs before staging; no wholesale dependency upgrades for the rescope. |

## Documentation and reference checklist

| Mark / owner | Files or area | Required change |
|---|---|---|
| CHANGE R1 | `CONSTITUTION.md` (formerly `vyom-12-week-sprint-plan.md`), `AGENTS.md` | [x] Consolidate active constitution/agreement; remove conflicting imperative reset, mandatory S1 stack, S3 RAG and obsolete fixed sprint sequencing from active instructions. Keep historic evidence clearly separated, not executable guidance. Do not rerun the historical reset. |
| CHANGE R1 | `docs/IMPLEMENTATION_PLAN.md`, `TRACKER.md`, `scripts/check-docs.py` | [x] Validate active R dependencies/status/evidence and new gate below; permit documented partial state. Old budget checks are historical only. Split R4a into bounded reviewable increments before implementation without inventing another backlog. |
| CHANGE R1 | `docs/VERIFICATION.md` | [x] Replace active cost/RAG/Jev/full-stack sprint gates with resource lifecycle, scope, partial/freshness, ten diagnoses, issue deduplication/recovery and background-job gates. Retain old results as history. |
| CHANGE R1 | `docs/ARCHITECTURE.md`, `MCP_INTEGRATIONS.md`, `OBSERVABILITY.md`, `LOCAL_DEVELOPMENT.md` | [x] Align request/collection/job paths and optional telemetry requirements, eliminate unscheduled domain expansion and stale progress claims. Preserve tested upstream implementation details. |
| CHANGE R1 | `docs/design/DESIGN.md`, `docs/diagrams/*` | [x] Replace old surface schedule and mark old diagrams/mocks as historical references at point of use. Spend/RAG/S6 visuals cannot remain current architecture. Regenerate diagrams only when actual implementation warrants it. |
| REMOVE from active guidance; RETAIN as historical reference | `docs/design/mockups/Spend.dc.html`, out-of-scope parts of Main/BlastRadius, old diagram JSON/HTML/SVG | Do not implement spend, forecasts, generic compliance or speculative services from these assets. No deletion is needed to remove their authority. |
| RETAIN | `README.md`, canonical `assets/branding/`, `docs/BRANDING.md` | README remains final-product description only by owner instruction. Put status in tracker/handoff; preserve original logo. |
| RETAIN | `docs/sessions/*`, `DECISIONS.md`, `RESCOPE_AUDIT.md` | Keep historical evidence accurate; annotate superseded decisions through new records rather than changing old results. |
| RETAIN separately | `learning/*`, `.archify/*` generated references | Educational apps/graphs are not production implementations or delivery gates. Check generated artifacts before staging; don't migrate tutorials into runtime or blindly delete them. |

## Cross-cutting gate requiring an explicit roadmap home

Add **R10 — operational recovery and identity/exposure gate** to the active plan. This preserves requirements already accepted in the old constitution rather than introducing a new product pillar. It is mandatory before multi-user access, remote exposure or claims of tenant isolation; its persistence/scope safeguards are implemented in R2 onward, not postponed to R10.

- [ ] Postgres backup/restore and migration rehearsal retains resources, evidence, issues and citations.
- [ ] Verified identity/membership, connection grants, current-grant checks on live and historical reads, jobs and conversations; cancellation/revalidation after revocation.
- [ ] Two-workspace denial tests, credential/session isolation, bounded retention and sanitized audit events.
- [ ] Production rejects fixed operator mode; private localhost access persists until this gate passes.

External security-signal ingestion is **deferred**, not silently covered by R5/R8 configuration checks. Choose one source, scope, event schema, deduplication and incident-evidence policy only when the Kubernetes loop and deterministic posture are useful. Remote enrollment, broad alert routing and a SIEM pipeline remain outside this immediate implementation sequence.

## Execution order

The [implementation plan](IMPLEMENTATION_PLAN.md) owns the order and the [tracker](TRACKER.md) owns status; this map does not repeat them. Keep one active implementation task; do not implement every unchecked row at once.
