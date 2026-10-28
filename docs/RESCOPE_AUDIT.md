# Repository rescope audit — 29 October 2026

Scope: tracked and untracked source in the current working tree, excluding ignored environments and Git history. Existing modified files and staged deletions were preserved. This is a repository audit, not a new live verification of the prior S1 results.

## 1. Current architecture

React/TypeScript/Vite/Refine with shadcn/ui and Tailwind serves `/` and `/kubernetes` (`frontend/src/App.tsx`). FastAPI (`backend/src/vyom/api/app.py`) exposes health, agent configuration, chat and direct pods. The direct HTTP Kubernetes Table collector (`collectors/kubernetes.py`) requests metadata and status without pod specs; it reads one configured namespace on every request, with pagination and bounded output. The browser polls; there is no persistent inventory or collection scheduler.

`agent/graph.py` runs a bounded LangGraph proposal → validated MCP call → cited answer. `agent/model.py` wraps the configured model. `mcp_client/` owns upstream discovery, schema validation, scoped credentials and result projection. `context.py` supplies fixed server-side development scope; production refuses this resolver. `evidence.py` normalizes source, time, resource items, coverage and sanitized errors. Evidence is transient. One Helm chart packages API/UI, pinned Kubernetes MCP and authenticated proxy, collector token refresher and RBAC. Separate vendor charts run Prometheus, Loki, Tempo, Alloy and Grafana. No database, migrations, AWS collector, security engine or investigation persistence exists.

## 2. Components that fit

| Pillar | Reuse | Gap |
|---|---|---|
| Inventory | Direct pod collector, trusted scope, table UI, pagination and coverage tests | Durable normalized resources, scheduler, workload ownership, detail and relationships |
| Investigation | LangGraph, model adapter, MCP host, citation validation, evidence UI, failure gates | Explicit workload skill, selective branching, richer safe evidence, history and ten diagnostic labs |
| Security | Scope enforcement, safe projection and deployment RBAC | Deterministic rule engine, policy inputs, findings, evidence and UI; existing safeguards are not product posture checks |

## 3. Out-of-scope components

No deployed FinOps domain was found. Pending cost collection, spend UI, mandatory RAG/Qdrant/embeddings, Jev evaluation and broad integration expansion belong outside the active roadmap. Learning exercises stay separate and receive no product acceptance credit. The existing telemetry stack is useful optional tooling; removing it immediately would break existing scripts and gates. Decouple its installation before claiming a minimal deployment.

## 4. Legacy reference classification

Search with `rg -n -i 'cloud[-_]compass|cloud[-_]cost[-_]compass|finops|cost|budget|forecast|azure|gcp|sca|sbom'` across repository text (excluding lockfiles for review noise). No active Cloud Compass module/name was found. Substring matches such as scaling are not product references.

| Location / meaning | Classification | Action |
|---|---|---|
| Constitution, implementation plan, tracker, architecture: future cost/S4 and RAG/S3 | remove from active scope | Supersede old delivery order explicitly; retain historical acceptance records |
| `frontend/src/components/vyom/sidebar.tsx`: Spend, Runbooks sprint promises | remove/defer | Navigation cleanup in R1 follow-up |
| `docs/design/mockups/Spend.dc.html`, other mockups and diagrams | defer | Historical design references only; remove from active product guidance before UI work |
| `docs/design/DESIGN.md`: spend/forecast and old surface schedule | remove/defer | Rescope overrides schedule; retain typography/tokens |
| `docs/MCP_INTEGRATIONS.md`: additional FinOps domains | remove | No general integration roadmap |
| `docs/DECISIONS.md`, sessions: historical choices | retain | Add explicit supersession; do not rewrite past evidence |
| `learning/`: token cost, examples and budget explanations | retain internally | Not billing product capabilities |
| Backend call/time/output budgets, telemetry queue limits | retain internally | Operational safety requirements |
| Azure/GCP/SCA/SBOM exclusion lists | retain | Explicit non-goals |
| Provisioning spend authorization | retain internally | Chargeable infrastructure still requires task-specific authorization |

## 5. Recommended removals

Remove disabled Spend navigation and future runbook promises, obsolete planned-service README diagram and mandatory vector-store roadmap. There are no cost handlers, migrations or collectors to delete. Preserve tested telemetry code; separately make optional exporters/stores and install gates independent. Do not delete upstream MCP, model integration, existing tests or learning material merely because inventory becomes primary.

## 6. Moves and renames

Keep current small modules until their consuming slice needs a change. Introduce `inventory/` for normalized contracts and persistence orchestration; retain the collector adapter until a move has working import/tests. Introduce `investigations/skills/kubernetes/` when implementing `investigate_workload`, reusing `agent/`. Add `security/` only for the first deterministic rule. Rename Today to Overview and the pod surface to Kubernetes inventory without implying full inventory exists. Preserve `/kubernetes` compatibility. No wholesale directory rewrite.

## 7. Schema impact

Add Postgres and versioned migrations; there is no old database to migrate. Start resources, relationships, collection_runs and evidence; add investigations/steps and security rules/findings with their respective features. Use the current trusted workspace as tenant boundary, not a browser-supplied tenant. Scope every query and composite foreign key. Resource identity must include connection/cluster and native UID so delete/recreate with the same name cannot inherit old relationships. Existing MCP name-based IDs cannot alone prove identity across recreation; preserve provenance and disclose unresolved identity.

Store normalized allowlisted properties, not arbitrary provider payloads. Index scoped type/name/location and both edge endpoints. Collection failure must not delete resources or refresh last_seen; only complete authoritative scans can mark absent resources, with reconciliation tests. Keep observation time, collection time, coverage, denial and stale state distinct. Retention and schema migration/restore tests are required before durable history is accepted.

## 8. UI impact

Target Overview, Inventory, Resource detail, Investigations and Security. Reuse tokens, logo, table and evidence components. Add routes only with real APIs. Resource detail must combine ownership, health, freshness and evidence before offering workload investigation. Security remains unavailable until deterministic findings exist. Remove sprint promises and sample statistics; keep Ask Vyom scoped to the three pillars.

## 9. Test impact

Preserve existing collector, evidence, context, MCP/model/graph and telemetry tests. Add persistence isolation, UID recreation, partial scan reconciliation, stale/denied distinction, relationship scope and scheduler overlap tests. Add Kind labs with expected evidence and cleanup for ten workload failures. Test diagnosis against evidence rather than exact prose; unsupported or insufficient evidence must produce limitations. Existing pod-status chat is not proof of root-cause diagnosis. AWS Stubber fixtures and later explicitly authorized sandbox gates follow the Kubernetes slice. LocalStack parity is never assumed.

## 10. Migration sequence

1. R1: adopt this scope and audit; finish navigation/product-copy cleanup and optional telemetry packaging independently, preserving tests.
2. R2: Postgres foundation, normalized models and scoped persistence; adapt current direct pod evidence; test collection failure semantics.
3. R3: workload/ReplicaSet/Pod relationships and detail first, then remaining Kubernetes inventory, configurable collection freshness and read-only metadata permissions. No Secret values, literal environment values or unrestricted events/logs.
4. R4: implement one bounded `investigate_workload` skill; inventory supplies context, authorized live tools verify missing/stale facts. Add labs incrementally until ten cases pass live with inspectable evidence.
5. R5: deterministic Kubernetes rules and findings (precise security/reliability/configuration categories).
6. R6–R7: only after R4 passes, native AWS inventory then connectivity. Build reproducible fixtures before any chargeable sandbox.
7. R8–R9: AWS checks and cross-platform identity relationships. ALB/instance diagnosis follows connectivity; broaden only with measured gates.

Reachability Analyzer creation/start is not a read-only action: MVP may consume existing authorized results, not silently create paid analyses. Log/command/environment inspection requires a safe projection and separately scoped identity; this specification does not authorize raw values or unrestricted logs. Framework mappings are metadata, not certification. IAM wildcard checks must not claim effective permissions from a single statement.

The rescope is accepted; implementation details above are recommendations until verified. No AWS expansion, new runtime capability or completed MVP is claimed by this audit.

Follow-up: the [repository-wide overhaul change map](OVERHAUL_CHANGE_MAP.md) expands this audit for continuous operations, with file-level actions and the restored identity/recovery gate.
