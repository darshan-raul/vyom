# Current handoff

Updated 2026-10-29; latest session [2026-10-29-07](sessions/2026-10-29-07.md).

R1 is complete. The README now leads with the Kubernetes deployment topology (cluster/namespaces, workloads, dependencies and mappings), with PNG/SVG/interactive HTML. The continuous-operations workflow is a separate collapsible section. Diagram artifact/browser checks and light/dark visual review passed in session 07; no runtime changes were made. The documentation checker validates HTML image targets too. README remains final-product language; current runtime still has transient pod inventory and MCP questions, without Postgres.

Required checks passed: seven docs regression tests, docs links/fences/roadmap, frontend typecheck/lint/build, all shell syntax, Helm lint and none/metrics/full rendering, invalid profile rejection, SVG XML and visual raster review, fresh Kind none and metrics application gates. The first metrics scrape timed out; observed config reload took three minutes, so the gate now waits up to five. Retry passed including Prometheus API scrape. [Evidence](sessions/evidence/r1-profiles-2026-10-29.txt) retains the failed attempt. Full telemetry live regression and live model calls were not run. No hosted README/browser render claim.

Next task: R2 scoped Postgres resource/evidence foundation. Read its [implementation section](IMPLEMENTATION_PLAN.md#r2--scoped-postgres-resource-and-evidence-foundation), [architecture](ARCHITECTURE.md) and relevant [file change map](OVERHAUL_CHANGE_MAP.md) entries. First scope the migrations and consumed resource/relationship/collection/evidence repository increment, including workspace isolation, native UID recreation and transient citation compatibility. Record the next session and verification before edits. R2 requires real Postgres transaction/migration/restore checks and persisted citations after restart; fixtures alone cannot close it.

The disposable vyom-r1 cluster was removed; existing kind-vyom and kind-apollo11 remain. Scripts used an isolated kubeconfig, no model key and internal/localhost access. No commits, tags or pushes. No new blocking owner decision.
