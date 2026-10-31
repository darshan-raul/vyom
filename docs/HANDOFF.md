# Current handoff

Updated 2026-11-01; latest session [2026-11-01-02](sessions/2026-11-01-02.md).

R3 is split into R3.1–R3.6 in [the plan](IMPLEMENTATION_PLAN.md#r3--scheduled-kubernetes-inventory-and-workload-detail) and is partial. Done:
- R3.1 ([2026-11-01-01](sessions/2026-11-01-01.md)): per-kind `Projection` collectors for Deployment, ReplicaSet and Pod (`SWEEP`, owners first); typed controller `owner`; `owns` edges (KINV01, KINV02); collector Role `vyom-collector-workload-reader`.
- R3.2 ([2026-11-01-02](sessions/2026-11-01-02.md)): `backend/src/vyom/inventory/sweep.py` runs in the API lifespan when the operator file has `inventory` (chart `collector.sweep`, default 60 s); migration 0003 `collection_leases` and `collection_health`; per-kind exponential backoff (KINV03).

Checks: `./scripts/postgres-test.sh` (43 passed); offline `pytest` (144 passed, 41 skipped); ruff; `helm lint`/`template`; `bash -n`; docs checker; Kind `vyom-check.sh` 24 PASS, 1 SKIP (Prometheus, none profile), including stored Deployments, ReplicaSets and pod owners equal to kubectl before any API request.

Known limits: `GET /api/kubernetes/pods` still collects per request (R3.3 moves it to stored reads). The chart runs one API replica, so multi-replica leasing is proven in tests only.

Next task: R3.3 stored inventory API — list with kind/name/health filters and cursor pagination, resource detail with owner chain, owned resources and per-kind freshness from `collection_health`, all read from Postgres under the trusted context; switch the pods route to stored state with explicit stale/denied/never-collected/empty states. No blocking owner decision.
