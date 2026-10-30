# Current handoff

Updated 2026-10-30; latest session [2026-10-30-02](sessions/2026-10-30-02.md).

R2 is done (R2.1 in [2026-10-29-09](sessions/2026-10-29-09.md), R2.2 in [2026-10-30-01](sessions/2026-10-30-01.md), R2.3 in [2026-10-30-02](sessions/2026-10-30-02.md)):
- `backend/src/vyom/inventory/`: versioned SQL schema (`0001_inventory.sql`), migration runner and CLI (`python -m vyom.inventory.migrate`), workspace-scoped `InventoryStore` with native UID identity and bounded run retention (`DEFAULT_MAX_UNREFERENCED_RUNS = 500`), `DatabaseConfig` and `Database` connection manager.
- API & collector persistence: `GET /api/kubernetes/pods` and chat tool rounds persist collections to Postgres (`PodsView.persisted`); `GET /api/citations/{evidence_id}/{item_id:path}` resolves citations from stored runs across API restarts and supports legacy name-based item IDs.
- Helm chart & Kind gate: `deploy/chart/vyom/templates/postgres.yaml` packages digest-pinned `vyom-postgres` (restricted non-root security context, 1 GiB PVC, mounted `Secret/vyom-postgres`) and suspended `CronJob/vyom-migrate` triggered as a controlled Job by `scripts/vyom-up.sh`. `scripts/vyom-check.sh` verifies live persistence, citation resolution, idempotent migration Job, and `pg_dump`/`psql` restore on `kind-vyom`.

Checks: `./scripts/postgres-test.sh` (29 passed); offline `pytest` (136 passed, 27 skipped); `ruff check` and `ruff format --check` (39 files); frontend `typecheck`, `lint`, `build`; `helm lint` and `helm template`; `bash -n scripts/*.sh`; `KUBE_CONTEXT=kind-vyom ./scripts/vyom-check.sh` (24 PASS); `python3 scripts/check-docs.py` and unit tests.

Next task: R3 — Scheduled Kubernetes inventory and workload detail. Read [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md#r3--scheduled-kubernetes-inventory-and-workload-detail) and [OVERHAUL_CHANGE_MAP.md](OVERHAUL_CHANGE_MAP.md). No blocking owner decision.
