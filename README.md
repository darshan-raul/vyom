# Vyom

A progressively built AWS + Kubernetes intelligence cockpit: ask a question, inspect live read-only evidence, and understand the answer.

**Current state:** documentation and architecture planning only. The previous implementation was removed. No application, deployment, or live integration is delivered yet.

## Start here

1. [Constitution](vyom-12-week-sprint-plan.md) — scope and six-sprint delivery order.
2. [Agent agreement](AGENTS.md) — how coding sessions work.
3. [Implementation plan](docs/IMPLEMENTATION_PLAN.md) — task details and acceptance.
4. [Tracker](docs/TRACKER.md) — authoritative task status and evidence.
5. [Current handoff](docs/HANDOFF.md) — where the next session starts.
6. [Architecture](docs/ARCHITECTURE.md) — intended S6 design and detailed diagrams.
7. [Verification](docs/VERIFICATION.md) — what constitutes proof.
8. [MCP integrations](docs/MCP_INTEGRATIONS.md) — upstream ownership, dual execution paths and deployment/auth gates.
9. [Decisions](docs/DECISIONS.md) — open choices and accepted implementation decisions.

First milestone: on Kind, ask which pods are unhealthy in a demo namespace and receive an answer citing the upstream Kubernetes MCP server through Vyom’s MCP client; the resource view uses a direct SDK path. No runtime setup commands exist yet; S1 will introduce and verify them.
