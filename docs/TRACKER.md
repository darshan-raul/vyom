# Execution tracker

This is the sole status ledger. Details and acceptance are in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Constitution wins on conflicts.

States: `pending`, `in_progress`, `blocked`, `done`, `deferred`. `blocked` requires an exact retry condition; `deferred` requires an explicit scope/date decision. `done` requires linked verification, not merely code. Session IDs refer to `docs/sessions/`.

## Reset and planning

| ID | Task | Status | Session | Evidence / next action |
|---|---|---|---|---|
| R0 | Remove previous project working files | done | prior reset | Constitution reset evidence; Git metadata and protected environment directories retained |
| P0 | Fresh guidance, implementation plan, tracker, handoff and architecture sources | done | [2026-10-03-01](sessions/2026-10-03-01.md) | Documentation consistency check; six detailed Mermaid views; interactive draft structural checks 9/9. Interactive diagram browser review is an optional note in [diagrams/README.md](diagrams/README.md), not a tracked task |
| P2 | MCP host/client architecture revision (planning only) | done | [2026-10-03-02](sessions/2026-10-03-02.md) | Constitution, 38-task roadmap, responsibilities/auth/deployment and seven Mermaid views synchronized; doc checks pass; interactive draft direct checker 9/9 |

## S1 — Smallest real agent

| ID | Task | Depends on | Status | Session | Evidence / blocker / next action |
|---|---|---|---|---|---|
| S1.1 | Fresh development scaffold | — | pending | — | — |
| S1.2 | Evidence, MCP client and trusted context | S1.1 | pending | — | — |
| S1.3 | Upstream Kubernetes MCP on Kind | S1.2 | pending | — | — |
| S1.4 | Initial reasoning adapter | S1.2 | pending | — | — |
| S1.5 | Bounded graph and MCP-backed chat | S1.3, S1.4 | pending | — | — |
| S1.6 | Direct Kubernetes evidence view | S1.5 | pending | — | — |
| S1.7 | Fresh Kind packaging | S1.5, S1.6 | pending | — | — |
| S1.8 | S1 live gate and walkthrough | S1.7 | pending | — | — |

## S2 — AWS and EKS evidence

| ID | Task | Depends on | Status | Session | Evidence / blocker / next action |
|---|---|---|---|---|---|
| S2.1 | EKS deployment and AWS MCP connectivity | S1.8 | pending | — | — |
| S2.2 | Direct EC2 inventory and AWS MCP investigation | S2.1 | pending | — | — |
| S2.3 | Workload and node health | S2.1 | pending | — | — |
| S2.4 | Current resource metrics | S2.3 | pending | — | — |
| S2.5 | CloudWatch EC2 metrics | S2.2 | pending | — | — |
| S2.6 | S2 dual-path gate and teardown rehearsal | S2.2, S2.3, S2.4, S2.5 | pending | — | — |

## S3 — Bedrock, runbooks and history

| ID | Task | Depends on | Status | Session | Evidence / blocker / next action |
|---|---|---|---|---|---|
| S3.1 | Bedrock reasoning | S2.6 | pending | — | — |
| S3.2 | Curated corpus and embeddings | S3.1 | pending | — | — |
| S3.3 | Qdrant ingestion and retrieval | S3.2 | pending | — | — |
| S3.4 | Minimal Postgres history | S3.1 | pending | — | — |
| S3.5 | Graph retrieval and evaluation | S3.3, S3.4 | pending | — | — |
| S3.6 | Direct-SDK observation schedule | S3.4 | pending | — | — |
| S3.7 | S3 live gate | S3.5, S3.6 | pending | — | — |

## S4 — Investigation and cost

| ID | Task | Depends on | Status | Session | Evidence / blocker / next action |
|---|---|---|---|---|---|
| S4.1 | Events and relationships | S3.7 | pending | — | — |
| S4.2 | Bounded multi-server investigation | S4.1 | pending | — | — |
| S4.3 | Daily cost collection and questions | S3.7 | pending | — | — |
| S4.4 | Two deterministic findings | S4.1 | pending | — | — |
| S4.5 | Optional Jev evaluation | S4.2 | pending | — | — |
| S4.6 | S4 live gate | S4.2, S4.3, S4.4, S4.5 | pending | — | — |

## S5 — Reliability baseline

| ID | Task | Depends on | Status | Session | Evidence / blocker / next action |
|---|---|---|---|---|---|
| S5.1 | Release and upstream compatibility automation | S4.6 | pending | — | — |
| S5.2 | Runtime and integration hardening | S5.1 | pending | — | — |
| S5.3 | External backup and native restore | S3.7 | pending | — | — |
| S5.4 | Answer and integration fault evaluation | S5.2, S5.3 | pending | — | — |
| S5.5 | S5 operational gate | S5.4 | pending | — | — |

## S6 — Identity and tenant boundary

| ID | Task | Depends on | Status | Session | Evidence / blocker / next action |
|---|---|---|---|---|---|
| S6.1 | Keycloak login | S5.5 | pending | — | — |
| S6.2 | Membership resolver and migration | S6.1 | pending | — | — |
| S6.3 | Grants and MCP connection isolation | S6.2 | pending | — | — |
| S6.4 | Persisted and asynchronous isolation | S6.3 | pending | — | — |
| S6.5 | Audit, credentials and identity recovery | S6.4 | pending | — | — |
| S6.6 | S6 isolation and exposure gate | S6.5 | pending | — | — |
