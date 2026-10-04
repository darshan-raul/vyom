# Decisions

The constitution already specifies the product stack and sprint boundaries; do not duplicate its decision log here. This file records only fresh implementation choices and unresolved inputs. Proposed choices are not authorization or delivered functionality.

| ID | State | Choice / question | Resolve by | Consequence |
|---|---|---|---|---|
| P01 | Open | Initial OpenAI-compatible endpoint, model, API-key injection and acceptable development data processing | S1.4 | Real tool-call compatibility must pass; never ask for a key in chat |
| P02 | Proposed | Fresh directories: `frontend/`, `backend/` (API + agent + MCP client + SDK collectors), `tests/`, `deploy/`, `scripts/` | S1.1 | Create only when used; upstream Kubernetes MCP is a separately pinned image |
| P03 | Open | Available Kind/container tooling and namespace for controlled test workloads | S1.1 | Check local tooling before publishing setup commands |
| P04 | Open | EKS reuse/create, AWS account, IAM provisioning authority, spend budget and teardown owner | S2.1 | No chargeable provisioning inferred from a documentation request |
| P05 | Open | In-region Bedrock model/embedding IDs, access and data-handling checks | S3.1 | Model selection is verified at implementation time |
| P06 | Open | Private host-to-upstream transport/authentication and explicit Kubernetes ServiceAccount auth mode | S1.2; harden S6.3 | Verify selected upstream release; no tenant-header trust, token passthrough or model-controlled endpoint |
| P07 | Open | Alpha retention, backup destination, restore objectives and encryption | S5.3 | Backups must be outside cluster; S3 bucket is a possible choice, not mandated here |
| P08 | Open | Jev gateway geography, retention, redaction and benchmark threshold | S4.5 | Default remains disabled unless activation gate passes |
| P10 | Open | Pin observability chart/image versions; validate PVC/storage/retention/compaction, discovery, endpoint controls and private Grafana credentials | S1.9; repeat S2.1 | Initial 48h/100% demo sampling is bounded but unmeasured; no Kafka or HA assumed |
| P11 | Open | Re-estimate S1 and aggregate dates/capacity after clean Kind stack installation | S1.8 | 250h means 12.5 weeks at 20h/week; twelve-week target requires an explicit adjustment |
| P12 | Open | Operator-only versus tenant-visible telemetry access and current-grant enforcement | S6.3 | Keep shared operator stores/Grafana private until exposed surfaces pass isolation/revocation gates |
| P09 | Open | Keycloak realm/client, HTTPS hostname, credential segregation and whether Vault is needed | S6.1 | No old realm IDs or domain assumed |

For each resolved entry record: date, accepted/proposed status, task, decision, reason, alternative, consequences, and evidence. Owner acceptance is required for changes to scope or constitutional constraints; routine implementation details can be decided and documented by the implementing agent.

## Accepted MCP architecture revision — 2026-10-03

Owner decision, recorded in [session 2026-10-03-02](sessions/2026-10-03-02.md) and the constitution:

| ID | State | Decision | Rationale / consequence | Tasks |
|---|---|---|---|---|
| MCP01 | Accepted | Vyom is an MCP host/client; no production custom MCP protocol servers | Replace planned FastMCP ownership with existing client SDK and upstream integrations | S1.1–S1.3 |
| MCP02 | Accepted | Prefer containers/kubernetes-mcp-server, self-hosted in the target cluster with scoped ServiceAccount/RBAC | Pin upstream, restrict read-only tools and private exposure; scope decisions are Vyom's responsibility | S1.3, S1.7, S2.1 |
| MCP03 | Accepted | Use AWS-managed MCP / appropriate AWS-provided capabilities for agent investigations | No general-purpose Vyom AWS wrapper; prove resource tool coverage and scoped workload credentials | S2.1–S2.2 |
| MCP04 | Accepted | Direct SDK/API path for deterministic product work; normal libraries for persistence/internal logic | MCP is not a universal internal protocol; preserve independent failure behavior and shared evidence semantics | S1.4, S2, S3.6, S4.3 |
| MCP05 | Accepted | Later servers plug into the same configured client boundary | No extra GitHub/IaC/FinOps implementation scope now; educational servers stay separate | S1.2, S4.2; domains later |
| MCP06 | Planned implementation of accepted isolation rule | Separate upstream Kubernetes endpoints/ServiceAccounts per tenant grant scope initially; AWS account-bound credentials | Avoid treating a shared broad identity or tenant header as provider authorization; verify before S6 completion | S6.3–S6.4 |

Open integration inputs: select/pin upstream version and safe pod result projection (S1.3); choose supported endpoint authentication/TLS (S1.2); verify AWS endpoint region/data handling, read capabilities and unattended credential renewal (S2.1). Source checks are in [MCP_INTEGRATIONS.md](MCP_INTEGRATIONS.md). These decisions replace only the former MCP ownership/universal collection assumptions, not the six-sprint scope or model-provider schedule.

## Observability scope revision — 2026-10-04

Owner-required Loki, Prometheus, Grafana and OTel tracing are accepted scope in the constitution. Its specified design uses Tempo for traces and Alloy for OTLP/log collection, single-instance PVC-backed stores, private access and two starter dashboards from S1; EKS follows S2 and hardening S5. These are planned, undelivered choices, not measured sizing or deployment evidence. See [design](OBSERVABILITY.md) and [planning session](sessions/2026-10-04-01.md).

S1.9 adds 10 task hours and is a prerequisite of S1.7, while S1.8 remains the live closing gate. Existing task IDs and intelligence gates are preserved. S2–S6 instrumentation, recovery and telemetry authorization are acceptance within their current budgets, subject to re-estimation. Agent analytics over the telemetry stores remains deferred; observer log access never widens MCP permissions.

## Accepted brand asset — 2026-10-04

**BRAND01 — Accepted by owner:** use the supplied blue telescope/helm/clouds logo for Vyom branding, including README, application, diagrams and the future website. The canonical source is [assets/branding/vyom-logo.png](../assets/branding/vyom-logo.png); it is preserved unmodified. [Branding guidance](BRANDING.md) governs reuse and accessibility. This replaces any expectation that the logo must be newly generated after the reset; it adds no site implementation or deployment scope. Source-byte and embedded-diagram verification is recorded in [session 2026-10-04-07](sessions/2026-10-04-07.md).
