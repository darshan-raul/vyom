# Vyom product constitution

Updated 29 October 2026. This is the sole scope and delivery authority, subordinate to current owner instructions. The filename remains stable for existing links; there is no fixed twelve-week commitment. Prior S1 implementation evidence remains in session records. The historical reset and superseded sprint instructions must not be executed again.

## Product

Vyom is a read-only AWS + Kubernetes operations station for DevOps engineers, SREs, cloud engineers and platform engineers. It continuously observes authorized infrastructure, detects meaningful changes, failures and configuration risks, and performs evidence-driven investigations. Its permanent pillars are **Inventory, Investigation, Security**.

Inventory is a normalized local representation of resources and relationships. Native APIs populate it without an LLM or MCP dependency. Deterministic detectors create findings and tracked issues; bounded agent skills investigate them. Users can ask operational questions and continue an issue investigation in natural language. Recovery requires fresh evidence, not a model's declaration. Configuration findings and external security detections are not automatically confirmed incidents.

## Delivery order and acceptance

The [implementation plan](docs/IMPLEMENTATION_PLAN.md) defines dependency-ready increments. The [tracker](docs/TRACKER.md) alone owns status. Deliver:

1. Coherent documentation and reproducible local packaging.
2. Workspace-scoped Postgres resources, relationships, collection runs and evidence.
3. Scheduled Kubernetes inventory, workload detail, relationships and explicit freshness.
4. `investigate_workload` with ten reproducible diagnostic cases and resolving evidence citations.
5. One automatic Deployment change → unhealthy state → issue → bounded investigation → conversational follow-up → observed recovery loop.
6. Deterministic Kubernetes posture, then AWS inventory and `investigate_connectivity`, then AWS posture and cross-platform relationships.
7. Recovery and verified identity/grants before multi-user or remote exposure; scoped persistence and credential isolation apply from the first database change.

No AWS expansion before the Kubernetes diagnostic and automatic-loop gates. No completed task without its acceptance evidence; fixture tests are not live gates. Split implementation into small reviewable increments and keep one active implementation task. Do not infer a fixed deadline from the legacy filename.

## Architecture

React + TypeScript + Vite + Refine + shadcn/ui + Tailwind; FastAPI; Postgres primary state; LangGraph for bounded investigation; pinned upstream Kubernetes MCP for agent tools. One application chart, Kind first. Use existing upstream/AWS-provided MCP integrations where useful; do not implement a general-purpose production MCP server or AWS wrapper.

Native API collection, scheduling, normalization, relationships, security rules and dashboards are deterministic. MCP is an agent integration boundary, not the data plane. Tools provide live verification when stored context is missing or stale. Use Postgres for relationships and leased jobs; no graph database or broker is needed for this scope. Add tables/dependencies only when the current increment consumes them.

The [continuous operations design](docs/CONTINUOUS_OPERATIONS.md) governs issue episodes, recovery, suppression, deduplication, job limits and follow-up context. Store before/after evidence for meaningful changes. Partial/failed collections never imply removal or recovery. UID recreation must not inherit the old resource's relationships or episodes.

Prometheus provides useful health evidence; Loki, Tempo, Alloy and Grafana are optional. External telemetry systems are evidence sources, not replacements to build. Application logs/metrics remain bounded and sanitized; outages do not block collection or requests.

Use the explicitly configured model provider and private credentials. Preserve the existing model adapter; Bedrock is a separately verified provider increment rather than a prerequisite for inventory. Never silently fall back to external inference. RAG, embeddings and vector storage are deferred until document knowledge is a concrete requirement.

## Authorization and data boundaries

Browser/model input cannot supply authority. Server context supplies workspace, connection, account, cluster and namespace grants. Revalidate current authority for live tools, persisted evidence, conversation, jobs and citations. Scope every database query and relationship; do not rely on filters as authorization.

All infrastructure tools are read-only. No arbitrary shell/SQL/exec, mutations, Secret values, literal environment values or unrestricted events/logs. Each tool has reviewed arguments/results and bounded calls, time, context, tokens and output. Provider IAM/RBAC enforces scope independently. Collector, agent and observer identities remain distinct; scoped MCP sessions cannot cross authorized connections.

Secrets stay server-side and out of Git, frontend bundles, responses, fixtures, telemetry and handoffs. Store only reviewed projections. Never log raw questions, answers, tool bodies, sensitive headers/URLs or unsafe exception text. Bound retention and metric cardinality.

Keep local alpha Services internal and access localhost-bound. Production rejects fixed development identity. Verified identity, membership, current grants, revocation, two-workspace isolation and restore tests are mandatory before exposure. No public deployment, chargeable cloud provisioning, external recipient contact, Git commit/tag/push without specific user authorization. Local edits and verification are authorized by implementation requests.

## Product presentation

Use the owner's [canonical logo](assets/branding/vyom-logo.png) and [branding guidance](docs/BRANDING.md). Keep the [design system](docs/design/DESIGN.md); introduce surfaces only with real data. Overview shows issues, changes, freshness and investigation progress; Inventory, resource detail, Investigations/issue detail and Security complete the product. No sample statistics or speculative navigation.

README describes the intended final product, never completion status or upcoming work. Tracker, handoff and sessions report actual delivery; [local development](docs/LOCAL_DEVELOPMENT.md) carries setup and current runtime limits.

## Deferred and excluded

Cost/FinOps, budgets/forecasting, Azure/GCP, software composition/SBOM/vulnerability management, generic compliance certification, SIEM, observability storage platform, deployment/CI orchestration, autonomous remediation/writes, arbitrary MCP marketplace and general chatbot are outside the core.

Defer runbook RAG/vector stores, remote enrollment, broad security-signal ingestion and external alert channels until a specific three-pillar use case and gate justify them. Preserve security-vs-reliability categories; framework mappings are metadata, not certification. Reachability Analyzer may consume existing authorized results; starting paid analyses is not read-only authorization.
