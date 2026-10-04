# Verification contract

This is a test strategy, not a list of commands that already exist. Each implementation task must add and document its actual commands. Use a small offline suite for iteration and explicit live gates for integration.

| Layer | Required proof | First introduced |
|---|---|---|
| Build/static | Fresh dependency installation, frontend type/build checks, Python imports and lint, chart render | S1 |
| Contracts | Invalid input rejected; result states and evidence IDs preserved; clients cannot supply authority | S1 |
| Direct SDK collector | Pagination, resource bounds, denied/unavailable/partial outcomes; no prohibited fields | S1; AWS S2 |
| MCP host and agent | Pinned upstream/client compatibility, authenticated discovery/call, server-qualified allowlist and operation/argument validation; bounded execution; no answer inventing unavailable evidence; cited IDs exist | S1 |
| Live journey | Browser question → real model tool call → MCP client → upstream Kubernetes server → real cluster → cited answer; compare with kubectl | S1 |
| Observability | Pinned clean stack install, actual cluster/app metrics and allowlisted logs, owned chat trace and log/trace links; provider/MCP failure, telemetry outage/loss/recovery, payload/cardinality and duplicate-ingestion checks | S1; repeat EKS S2 |
| Providers | Same tool/evidence smoke on initial adapter and Bedrock; no silent external failover | S3 |
| Retrieval | Relevant/irrelevant queries, duplicate ingestion, version replacement, injection text, citation provenance | S3 |
| Persistence | Workspace-scoped reads/writes, restart survival, stale labels, idempotent observations | S3 |
| Investigation/cost | Loop limits, hypothesis separation, decimal arithmetic/date boundaries/pagination, Cost Explorer reconciliation | S4 |
| Operations | Separate AWS MCP/Kubernetes MCP/model/storage outages, direct path independence, fresh install/upstream upgrade, rollback, external backup restore | S5 |
| Isolation | Wrong/missing/expired JWT; cross-tenant IDs and retrieval; endpoint/credential/session isolation; direct SDK jobs/caches/checkpoints; revoked namespaces in retained history | S6 |

## MCP-specific acceptance matrix

| Gate | Required proof | Task |
|---|---|---|
| Upstream adoption | Runtime uses existing Kubernetes server and existing client SDK; no custom protocol implementation | S1.1–S1.3 |
| Private Kubernetes MCP deployment | Deployment, conditional Service, dedicated SA, Role/RoleBinding, explicit read-only tools, secure config, auth, probes/sanitized logs (NetworkPolicy optional, end of roadmap) | S1.3, S1.7 |
| Authority and safe output | Wrong namespace/caller, Secret access, writes/exec and unsafe tool selection denied; pod env/raw logs absent from model, UI, history and logs | S1.2–S1.3 |
| Independent deterministic path | SDK dashboard still collects while MCP is down; both paths share evidence identity/coverage semantics | S1.6, S3.6 |
| AWS managed integration | Real authenticated resource investigation, correct account/operation/region, endpoint/data-handling checks and credential renewal; no custom AWS wrapper | S2.1–S2.2 |
| Effective permissions | Read-only behavior enforced by provider IAM/RBAC and host policy, not annotations or prompts | S1–S2; S6 |
| Upstream changes | Pinned versions, tool/schema drift denial and controlled rollback; no auto-enabled tool discovery | S5.1 |
| Tenant transport safety | Scoped endpoints/identities, no pooled session/credential crossover, revocation before further reads; same constraints on SDK jobs and history | S6.3–S6.4 |

No MCP gate passes from direct-SDK-only results, mocks, a documentation-only MCP source or an educational server. Record unsupported upstream capabilities and exact retry conditions. Review permissions and network/auth controls for both Kind and EKS.

## Evidence rules

Record task, date, code/worktree state, exact command, environment, sanitized expected/actual outcome and limitations. Do not label a fixture as live. Do not upload raw prompts, credentials or operational payloads into evidence. Save concise textual results or redacted screenshots only when helpful.

For nondeterministic answers, assess properties: factual claims supported by cited evidence, source and time correctness, arithmetic, explicit limits and absence of unauthorized calls. Exact wording is not an assertion. Agree quantitative evaluation thresholds before marking S3/S5 gates complete.

## Sprint demonstrations

- S1: controlled unhealthy pod, matching live table and cited answer; denial and provider-failure demonstrations; clean Kind setup with the full observability stack. A real chat/failure must have applicable metrics, sanitized logs and owned spans in Grafana; synthetic OTLP is setup evidence only. Interrupt telemetry, show bounded application behavior plus independently observable loss and recovery, and inspect prohibited fields/duplicates.
- S2: same release on Kind/EKS; failed workload; current metrics comparison and explicit missing metrics; EC2 inventory including stopped instances; repeat the S1 telemetry gates on EKS, record storage/pins and inaccessible control-plane targets.
- S3: both reasoning adapters pass the same journey; live evidence + distinct runbook citations; restart preserves history; re-ingest is idempotent; inspect payload-free Bedrock/embedding/retrieval/database/vector/job signals and failure outcomes.
- S4: bounded investigation; service cost reconciliation; Jev on/off benchmark and explicit enabled/disabled decision; inspect investigation/cost and applicable Jev timings/outcomes.
- S5: restore into a clean deployment, rollback a bad release, fail dependencies deliberately and pass evidence evaluations; test alerts and telemetry storage/sampling/retention/loss/recovery.
- S6: two tenants, denial matrix and revocation on persisted evidence; Keycloak recovery; public ingress remains disabled until all relevant gates pass, including current-grant checks on exposed telemetry query/proxy/Grafana surfaces or evidence that shared operator telemetry remains private.

A sprint gate is not satisfied by its component task checkboxes alone. Record a separate end-to-end result.

## Observability evidence

Follow the six-step [S1 live gate](OBSERVABILITY.md#s1-live-gate). Record chart/image versions, environment, window, exact PromQL/LogQL/trace queries, sanitized trace ID and both navigation directions. Inspect owned HTTP/graph/model-client/MCP-client/normalization spans; require upstream internal spans only where pinned support is verified. External provider internals are not promised. Metrics are aggregate; optional exemplars are not universal request correlation. Missing token usage is unavailable, not zero.

Inspect signal storage as well as source configuration for credentials, prompts/answers/tool bodies, pod environment fields, unsafe errors and sensitive headers/URLs. Verify finite label sets and single log ingestion, node-local discovery and separate observer RBAC. Prove bounded queues/retries and application response during exporter/collector/store outage; use Prometheus scrape health and Kubernetes status to detect collector loss independently. Record drops and recovery without promising complete trace delivery during failure. Grafana auth/private access and internal endpoints must be checked; tenant filters alone cannot close S6 isolation.
