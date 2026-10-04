# Current handoff

Updated: 2026-10-04. Latest session: [2026-10-04-06](sessions/2026-10-04-06.md).

## Current state

Planning only. README now embeds a standalone architecture SVG with deployment boundaries, service icons, sprint labels and five primary connections. Individual workloads, stores, observability services and external dependencies are visible. Mermaid flowcharts were removed from README; detailed request/collection diagrams remain linked. Observability scope is synchronized across the constitution, 39-task implementation plan/tracker, architecture, verification, decisions, agent guidance and diagrams. The owner-supplied observability design moved to [OBSERVABILITY.md](OBSERVABILITY.md), matching the constitution's existing link. No runtime scaffold or deployed telemetry exists; all S1–S6 implementation tasks remain pending.

S1 requires real LLM/LangGraph/upstream Kubernetes MCP chat and live evidence plus Prometheus, Loki, Tempo, Grafana and OTel/Alloy. S1.9 (10h) prepares the stack after S1.1; S1.2–S1.6 instrument their owned paths. S1.7 depends on S1.9 as well as chat/table. S1.8 closes with real correlated chat/failure signals and independent telemetry loss/recovery, alongside the existing agent/RBAC gates. S2 repeats on EKS; S3–S4 instrument new paths; S5 hardens telemetry; S6 decides and tests telemetry access.

S1 estimates 40 task hours + 10 reserve; S2–S6 retain 30 + 10 each. At 20h/week, total 250h means 12.5 weeks, with twelve weeks still the target. Re-estimate after the first clean Kind stack installation; later-sprint instrumentation/hardening fits provisional budgets only. Do not drop either S1 gate to fit dates.

## Next task and first action

**S1.1 — fresh development scaffold**, when implementation is requested. Inspect local tooling/dependency documentation, then scaffold only frontend, FastAPI, existing-SDK MCP client module and minimal health/build checks. This session authorized documentation/diagram changes only.

Next prepare **S1.9**: inspect/pin vendor charts/images and actual defaults, storage/retention and access controls; install the stack on Kind and establish bounded instrumentation helpers. Follow [implementation plan](IMPLEMENTATION_PLAN.md) and observability design. Preserve upstream MCP/private transport/scoped identities and the independent direct-SDK table sequence after S1.5. No telemetry-store agent tools are scheduled.

## Unresolved inputs / limits

- Model endpoint/tool-call compatibility and private key injection; upstream MCP version, safe projection and transport auth remain S1 inputs.
- Observability versions, PVC/storage, retention/compaction support, node-local log discovery, finite resources/queues and private Grafana credentials require implementation-time checks. Initial 48h retention/100% bounded-demo tracing is unmeasured.
- Telemetry observer identity does not widen agent RBAC. No prompts, answers, tool bodies, sensitive headers/URLs or unsafe exception text enter telemetry; trace IDs are fields, not indexed labels.
- EKS/AWS provisioning authority, budget, endpoint/data-handling/capability checks remain S2 inputs. Telemetry visibility policy remains S6; shared operator stores stay private until exposed surfaces pass grant/revocation checks.

## Checks / external effects

`python scripts/check-docs.py`, `git diff --check` and SVG XML/internal-reference checks passed. Installed `rsvg-convert` rendered the SVG at 1200px and 760px widths; raster previews were visually inspected, with one label correction. No browser integration test was run. Earlier source-to-artifact bindings and both direct Archify checkers passed 9/9 with zero errors/warnings. Standard validation/atomic delivery failed due to child-process/empty-checker-receipt behavior; browser/visual acceptance for those HTML drafts and Mermaid rendering were not performed. See [diagram limits and retry commands](diagrams/README.md).

No application code, deployment manifests, live integrations, cloud resources, running application processes, commits, tags or pushes were created. S1.1 remains pending; documentation completion is not runtime acceptance.
