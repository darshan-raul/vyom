# Verification contract

The active [implementation plan](IMPLEMENTATION_PLAN.md) defines acceptance, and [tracker](TRACKER.md) records evidence. A code change, passing fixture or skipped integration check never proves live delivery. Historical S1 results remain in sessions, not as new roadmap gates.

## Required checks by increment

| Area | Proof |
|---|---|
| Documentation/packaging | Active roadmap IDs/dependencies/status validation, negative checker tests, shell syntax, chart profiles, frontend/backend checks, fresh Kind installation |
| Persistence | Real Postgres scoped queries/FKs, migrations and restore, UID recreation, atomic collection writes, immutable evidence and resolving citations |
| Inventory | Live authorized API comparison, resource relationships, scheduled updates with browser closed, partial/failed scans not deleting resources, freshness and scope denial |
| Workload skill | Ten named Kind failures with evidence-backed diagnosis, unknown/insufficient evidence, injected tool text, model/MCP failures and bounded calls |
| Continuous loop | One change→issue→automatic investigation→follow-up→recovery journey; deduplication, restart leases, flapping, stale results, partial collection, revocation and recovery races |
| Posture | Deterministic positive/negative/unknown cases, policy/version provenance, evidence/remediation and safe stale-data handling |
| AWS | Stubber fixtures plus specifically authorized live comparisons and connectivity failures; LocalStack compatibility proven per API; configuration distinct from observed traffic |
| Exposure | Restore with citations, verified identity/current grants, two-workspace denial and revocation across live/history/jobs/conversation, private credentials and production identity refusal |

## Evidence records

Record exact command, date, worktree state, environment, expected/actual result and limits in a session record. Keep credentials, questions, answers and provider payloads out of routine evidence logs. Fixtures and stored API examples must be sanitized. Evaluate factual support and citation resolution rather than exact generated prose. Rendering/keyboard/accessibility checks apply when UI surfaces change.

Use smallest meaningful checks first, then the task's required live gate. Optional full telemetry gates are independent from application/metrics profiles. Telemetry tests cover bounded export, absence of sensitive payloads, cardinality and continued operation during outages; Grafana/Tempo/Loki are not required to prove inventory functionality.

## Repeatable commands

```sh
python scripts/check-docs.py
python -m unittest discover -s scripts -p 'test_*.py'
bash -n scripts/vyom-up.sh scripts/vyom-check.sh scripts/observability-up.sh
helm lint deploy/chart/vyom
```

Run frontend `npm run typecheck`, `npm run lint`, `npm run build`, and backend `uv run ruff check .`, `uv run pytest -q` in their directories when relevant. [Local development](LOCAL_DEVELOPMENT.md) documents profile-specific installation/gates. Do not run scripts against an unrelated current Kubernetes context.
