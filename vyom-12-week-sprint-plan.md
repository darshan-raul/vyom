# Vyom: 12-week delivery plan

Prepared 3 October 2026; revised for a fresh implementation with intelligence in the first working slice. This plan is the sole project constitution. Previous implementation, agent guidance, decisions, and trackers do not govern the new build.

## Outcome and delivery order

Build a small, useful AWS + Kubernetes intelligence cockpit. The first working slice must already answer a natural-language question using live read-only MCP tool results, an OpenAI-compatible model endpoint, and LangGraph. Run it on Kind, extend it to AWS and EKS, introduce Bedrock and curated RAG in S3, then add deeper operational signals, hardening, and finally Keycloak/multi-tenancy.

Owner decision: S1–S2 use a simple server-side API key and configurable OpenAI-compatible endpoint. Bedrock arrives in S3 as the intended AWS inference path. This changes the former Bedrock-only early-alpha requirement; it does not remove the agent, MCP, or grounded-answer acceptance gates. Use a non-sensitive development account/cluster and bounded tool projections for the initial provider path.

Vyom's purpose is to connect operational evidence to an explainable answer and useful next checks. Tables and charts expose that evidence; chat and the agent are central product functionality. Reduce the number of sources, tools, documents, and supported questions to fit each sprint. Do not defer the entire intelligence layer.

Owner decision: remove all existing project files except this plan and begin from scratch, including removal of the old AGENTS.md, documentation, assets, implementation, and local generated state. Do not create backups or archives. Preserve only the choices expressed in this plan: Vyom's name, product goals, and the UI stack **React + TypeScript + Vite + Refine + shadcn/ui + Tailwind**. Create any needed assets afresh.

The first milestone is a working personal agent, rather than the existing external-beta scorecard. The 12-week goal is a useful personal alpha with grounded AWS/Kubernetes chat, curated RAG, and a tested initial tenant boundary. Completing the entire existing beta backlog, broad monitoring coverage, and general production availability are outside this timebox.

Planning assumption: one developer with roughly 20 focused hours per week. Each two-week sprint has approximately 40 hours; reserve about a quarter for integration, failures, and demonstration. Weeks are relative to kickoff. If available time is lower, move the dates rather than increasing work in each sprint.

| Sprint | Weeks | Deliverable | Demonstration that closes the sprint |
|---|---|---|---|
| S1 | 1–2 | Fresh shadcn/ui app on Kind; LLM + LangGraph MCP host + upstream read-only Kubernetes MCP | Ask which pods are unhealthy; the agent calls a live tool and cites the returned resources |
| S2 | 3–4 | AWS-managed MCP integration, direct EC2 collection, EKS deployment, basic monitoring | Ask about EC2 instances and EKS workload health; inspect the supporting live evidence |
| S3 | 5–6 | Bedrock reasoning adapter, curated RAG with Qdrant/Bedrock embeddings, minimal history | Switch the configured reasoning provider, pass the same tool journey, and add cited runbook guidance |
| S4 | 7–8 | Bounded multi-tool investigation, daily cost queries, Jev evaluation | Investigate a demo failure or explain service spend using linked tool results; compare classification with/without Jev |
| S5 | 9–10 | Operational hardening and grounded-answer evaluation | Recover stored data, roll back a bad release, and pass provider/tool failure and answer-evidence checks |
| S6 | 11–12 | Keycloak, membership-based tenancy, and server-side access enforcement | Two test tenants have isolated tools, retrieval, chat history, accounts, clusters, and namespaces |

## Reset at the start of S1

The reset is an implementation task inside S1, not an additional preliminary sprint:

1. Remove the existing project working tree without creating a preservation commit, tag, backup, or archive. Keep this plan and the existing Git metadata/history/remotes. Environment-managed read-only directories are outside the project reset. Do not create commits or push changes unless explicitly requested by the owner for that action.
2. Remove the old frontend, backend services, connectors, inference/RAG code, shared contracts, tests, migrations, deployment manifests, Helm charts, Dockerfiles, infrastructure definitions, and implementation scripts from the active tree. Do not relocate them into a runtime `legacy/` folder or import them into the fresh application.
3. Delete the old brand assets, README, AGENTS guidance, architecture documents, and trackers. Create fresh documentation only as the new implementation needs it, subordinate to this plan. Do not carry forward historical decision logs or the previous beta dependency chain.
4. Generate a fresh frontend and backend scaffold, fresh dependencies and lockfiles, fresh tests, and one fresh deployment chart. Add features only when their sprint requires them.

The repository review supplies lessons and regression scenarios, including pagination, partial failures, selector matching, and server-controlled authorization. Reimplement those behaviors with new code and new tests. Existing passing tests and adapters are not carried forward as delivered functionality.

## Small initial architecture and UI

Build a new React/Refine application using **shadcn/ui** for chat, tool-result evidence panels, navigation, cards, resource tables, badges, filters, and dialogs. Keep consistent typography, spacing, loading/empty/error states, and responsive behavior from the first sprint. The first version is small in feature scope while retaining the intended UI quality.

Build one new browser-facing FastAPI backend that runs LangGraph and acts as an **MCP host/client**. The UI (and a future CLI) calls normal backend APIs. Agent-driven troubleshooting, investigation and interactive diagnostics preferentially use MCP capabilities through the backend's client. Vyom does not implement a production MCP protocol server or a general-purpose AWS MCP wrapper.

For Kubernetes, self-host a pinned existing implementation, preferably `containers/kubernetes-mcp-server`, inside the target cluster. It talks directly to the Kubernetes API using its own deliberately scoped ServiceAccount. For AWS in S2, connect to the AWS-managed MCP Server or an appropriate AWS-provided capability after verifying endpoint, authentication and required tool coverage. Do not assume an AWS documentation-only server can inspect resources. If a required capability is unavailable, record that gap and retry condition; do not build a general-purpose Vyom MCP server as a substitute.

**Two execution paths:** deterministic inventory, scheduled synchronization, dashboards, large structured pulls and calculations use direct AWS/Kubernetes SDKs/APIs where simpler and more reliable. PostgreSQL, Qdrant, persistence, embeddings and ordinary internal logic use normal libraries/APIs, not MCP. Agent exploration uses upstream MCP capabilities. Both paths normalize authorized, sanitized evidence into the same source/time/coverage contract, but neither depends on identical collection code or converts every backend function into an MCP tool.

S1 has UI, API/agent with an embedded MCP client, and the independently packaged upstream Kubernetes MCP Deployment. Vyom builds its UI/API images and pins the upstream server image/chart; it does not share a Vyom Python image with that server. A configured OpenAI-compatible endpoint supplies reasoning in S1–S2. Add Bedrock, Postgres and Qdrant in S3, with RAG inside the API. Keycloak remains S6 and Vault remains conditional. Basic MCP connection health and sanitized logs start in S1; broader operational hardening stays S5.

The MCP client owns connection lifecycle, protocol negotiation, tool discovery restricted by a host allowlist, argument validation, deadlines, size/call budgets, credential binding and result normalization. Use server-qualified tool identities to avoid collisions. Server URLs, credential references, account, cluster and namespace authority come from operator/server configuration, never prompts. Additional GitHub, Terraform/IaC, documentation, FinOps or domain MCP endpoints may use this boundary later; implementing them or a plugin marketplace is outside the six-sprint core. An educational MCP server may be built separately only on request and never becomes a production dependency or satisfies a sprint gate.

The first LangGraph workflow has one bounded tool round followed by an answer. Validate every proposed tool and argument before calling it, enforce server-configured scope, and link the final answer to the returned evidence. Missing model access or tool evidence produces an explicit unavailable response, not an ungrounded fallback.

Use a small provider adapter from S1. Configure provider, base URL, model, and a backend-only API key; never compile the key into Vite or expose it through browser requests/logs. Normalize messages, proposed tool calls, tool-result messages, errors, and token usage across the adapter. The endpoint/model must pass a real tool-call round trip and argument-validation checks; an OpenAI-compatible chat endpoint alone is not evidence of supported tool calling. Use the selected provider's native integration if its necessary features exceed the standard compatible API.

In S3, add the Bedrock implementation behind the same adapter, with an allowlisted model, region, IAM permissions, and data-handling validation. Preserve the graph, tool contracts, MCP client integrations, citations, and frontend. Run the same grounded-answer smoke suite on both adapters before switching the configured default. Provider translation and model-behavior differences require testing; this is not a promise that every model is interchangeable. Do not silently fail over from Bedrock to an external provider.

Keep reasoning and embedding configuration separate. Embeddings start in S3 with Bedrock, so S1–S2 do not require an embedding service or a later vector migration. Future embedding changes require model/dimension-specific collection handling and reindexing.

Tool results and retrieved text are evidence, not instructions. No arbitrary shell, SQL, Kubernetes writes, resource mutation, or model-selected external destinations. Bound tool calls, context size, output tokens, and request duration from the first agent demo.

Use one newly written deployment source: a small Helm chart with Kind and EKS values, plus fresh Vyom container definitions and a pinned upstream Kubernetes MCP dependency or deployment configuration. Enable only services that exist in the new implementation; nginx must have no dependency on future services.

The Kubernetes MCP deployment must specify a Deployment, ClusterIP Service when using network transport (prefer supported Streamable HTTP), dedicated ServiceAccount, namespace Role/RoleBinding with only required read verbs/resources, read-only tool configuration, probes/resources, sanitized logs/connection metrics and private config/credential mounts. No public MCP Ingress/LoadBalancer, developer-admin kubeconfig, cluster-admin role, mutation/exec tools, raw logs or Secret access. Nodes/cluster-wide reads require separately justified grants in S2. Pin and verify actual upstream version, flags, defaults and auth mode; a read-only hint is not authorization. NetworkPolicy (backend-only ingress, restricted egress) is optional end-of-roadmap hardening; if added, verify CNI enforcement and otherwise make no isolation claim. Use supported endpoint authentication/TLS or an existing authenticated proxy; do not implement a custom MCP auth server. Kubernetes API authentication must remain the server's scoped ServiceAccount, not accidental forwarding of a browser/Keycloak token.

From S6, bind each authorized tenant/connection to an isolated MCP endpoint/credential scope. Start with separate Kubernetes MCP deployments/ServiceAccounts per tenant grant scope rather than sharing a broad identity and trusting a tenant header; re-evaluate scope and invalidate pooled sessions on revocation. AWS connections similarly bind temporary credentials/roles to the authorized account. Backend policy and provider RBAC/IAM both enforce scope. Apply the same grants to deterministic SDK collection, stored evidence and background jobs. Permission expansion, especially writes, requires a later explicit use case, policy decision and tests; the entire current six-sprint core remains read-only.

The backend uses a fixed, server-configured operator context during the personal-alpha phase. The browser supplies filters, not authority. Keep that context behind a resolver interface so S6 replaces the resolver with verified JWT and membership resolution. Do not leave arbitrary tenant headers or tool arguments active in this path.

Include stable workspace, connection, AWS account, region, cluster UID, namespace, and resource identifiers in contracts from the beginning. An internal workspace ID allows future tenant-scoped persistence without implementing users, memberships, and onboarding now.

Before S6, access the UI through a localhost-bound Kubernetes port-forward using your existing cluster access. Application Services stay internal. Do not make the unauthenticated alpha available through a public Ingress or LoadBalancer. Production mode must refuse the development identity resolver.

AWS and Kubernetes collection are read-only from day one. Configure one explicit AWS account and initially `ap-south-1`; one cluster per running environment. The local and EKS deployments each monitor their own cluster first. Remote-cluster enrollment is later work.

## S1: make the smallest real agent work

**Week 1:** complete the reset, scaffold the shadcn/ui browser/API and MCP client, and connect the host to one allowlisted upstream pod capability in the Kind demo namespace.

**Week 2:** connect the chosen OpenAI-compatible endpoint and a minimal LangGraph tool workflow to chat, add evidence links, and make the full Kind installation reproducible. AWS collection begins in S2 so the fresh-start sprint remains small.

Work:

1. Complete the reset and scaffold React/TypeScript/Vite/Refine with shadcn/ui and Tailwind. Build Chat and Kubernetes views with an explicit development identity mode.
2. Define small HTTP/evidence contracts and MCP client integration boundaries for health, chat, and resource results. Include source identity, collected-at time, coverage, evidence IDs, and sanitized errors.
3. Deploy and configure the upstream Kubernetes MCP server for one bounded pod-list/health capability in a configured demo namespace. After the MCP-backed agent path works end to end (S1.5), implement a small direct Kubernetes SDK projection for the resource table. Match both paths to the same evidence contract and compare them with kubectl; do not expose Secrets, literal environment values or unrestricted event payloads to the model, UI, history or telemetry. Verify upstream response minimization before enabling the tool.
4. Implement the OpenAI-compatible reasoning adapter and a new LangGraph workflow: propose tool → validate/execute through the MCP client and upstream server → answer with evidence. Limit this first workflow to one tool round and a small set of supported questions.
5. Show the tools called and evidence behind the answer. A simple final-response HTTP path is sufficient; polished streaming is later work.
6. Build new Vyom images, pin the upstream Kubernetes MCP image and deploy the fresh chart on Kind. Configure the provider's base URL/model and inject its API key into the API workload at runtime through an ignored developer credential file or equivalent private mechanism. Provide only redacted placeholders in examples; no AWS Bedrock credentials are required in S1.

Acceptance:

- A clean checkout can build and reach chat and the live Kubernetes view through documented commands.
- The active application contains no imports or runtime dependencies on the discarded implementation. The UI visibly uses the new shadcn/ui component system.
- The Kubernetes MCP Deployment/Service/ServiceAccount/RBAC, read-only configuration, authenticated private transport, config handling, redacted logging are verified on Kind. Unauthorized callers, forbidden namespaces, writes/exec and Secret reads fail. No Vyom-owned MCP server exists in the runtime.
- Ask “Which pods are unhealthy in the demo namespace?” The live MCP result agrees with `kubectl`; the answer identifies supporting resource evidence and collection time.
- A controlled workload change changes both the direct-SDK table and a fresh MCP-backed answer with matching resource identity/time semantics. MCP unavailability does not break independent deterministic collection; chat reports the integration failure explicitly.
- Kubernetes denial, model-provider failure, unsupported requests, and missing evidence produce explicit limitations. The agent does not invent tool data or claim a confirmed root cause from status alone.
- Offline tool/model fixtures are visibly separate from the required live demonstration.
- No login screen, persistent history, metrics pipeline, RAG corpus, Bedrock setup, or tenant management is required to close S1. Working LLM chat, LangGraph, and MCP are required.

## S2: deploy on EKS and add easy monitoring

Move the same images and chart to a small development EKS cluster in `ap-south-1`. Use existing suitable development infrastructure where available; dedicated production provisioning comes later. Keep access private through port-forwarding.

Work:

1. Configure separate Kubernetes MCP and deterministic collector ServiceAccounts and bounded read permissions on EKS, retaining the pinned upstream deployment and private authenticated transport. Keep separate permission for nodes and other cluster-scoped objects.
2. Connect the MCP client to AWS-managed MCP / appropriate AWS-provided capabilities for read-only EC2 investigation; verify current endpoint/region, data handling, unattended workload authentication and live tool coverage. Use temporary workload credentials (IRSA for the EKS host/collector where supported) and current least-privilege IAM. Separately implement direct-SDK EC2 inventory for dashboards/sync, including stopped instances, pagination, correct region and partial/denied/unavailable states. Do not deploy a Vyom AWS MCP wrapper. Keep the API on the OpenAI-compatible provider; Bedrock IAM permissions are introduced in S3.
3. Add pod readiness, restart count, waiting/termination reason, deployment available replicas, and node readiness.
4. Add current pod/node CPU and memory through the Kubernetes resource metrics API, with explicit unavailable states when Metrics Server is absent.
5. Add bounded direct-SDK CloudWatch EC2 CPU/status-check queries and UI views; validate corresponding AWS-provided MCP coverage for interactive questions, recording unsupported capabilities explicitly. Make Kubernetes health and AWS inventory/metrics accessible through chat, with evidence and timing. Do not promise EC2 guest memory or filesystem usage without an agent.
6. Document EKS create/reuse, deploy, access, and teardown; include a budget check and clean-up of chargeable development resources.

Acceptance:

- Kind and EKS run the same application release and pinned Kubernetes MCP version with environment-specific configuration. AWS-managed MCP remains a remote dependency, not an EKS workload; endpoint location is verified separately from the ap-south-1 platform and target-resource region.
- A real AWS investigation traverses the MCP client and AWS-provided capability, with account/region/credential and write-denial checks. Direct inventory still works when MCP is down. Endpoint/auth/data-handling or capability gaps leave the affected gate unfinished; SDK success is not MCP acceptance.
- A failed demo pod produces the expected visible state.
- Current resource metrics match a contemporary `kubectl top` reading within collection timing limits.
- EC2 charts show the requested time window and source; missing metrics are not displayed as zero.
- Ask about EC2 instances or EKS workload health and receive a grounded answer with correctly scoped tool results.
- There is a useful AWS + Kubernetes intelligence cockpit by the end of month one.

## S3: add Bedrock, curated RAG, and minimal memory

Add the Bedrock reasoning adapter and validate it against the existing agent journey. Then add Qdrant, Bedrock embeddings, a small operator-curated runbook corpus, and Postgres for minimal chat/evidence/collection history. Keep retrieval in the API and ingestion as an operator-run job. Use a fresh authoritative migration directory with a version ledger. Defer broader AWS inventory expansion to keep this sprint bounded; begin with the smallest corpus and history schema if model activation takes time.

Work:

1. Add the Bedrock reasoning adapter, EKS workload IAM permissions, region/model configuration, and deployment validation. Verify tool-call/message translation, failures, usage reporting, and evidence quality using the same tests as the initial adapter.
2. Write approximately 5 short curated runbooks for supported health scenarios, including pending pods, image-pull failures, restarts, and node readiness. Record document ID, version, section, and source.
3. Implement chunking, Bedrock embeddings, workspace/model-version-scoped Qdrant collections, bounded retrieval, and an idempotent operator ingest command. No arbitrary uploads or crawling.
4. Add retrieval to LangGraph alongside live MCP evidence. Distinguish observed facts, possible explanations, and runbook next checks in the answer. A runbook does not prove a cause in the live cluster.
5. Store sessions, messages, citations, source/connection identities, bounded observations, and collection errors in Postgres. Scope repository queries and vector searches to the internal workspace.
6. Add a small idempotent direct-SDK scheduled observation job, freshness display, and persisted chat evidence; database/vector access remains through normal libraries. Do not claim a comprehensive change feed yet.
7. Add a compact answer-evaluation set, including relevant/irrelevant retrieval, unsupported questions, stale evidence, unavailable tools, and instructions embedded in retrieved text.

Acceptance:

- A configuration change selects Bedrock without altering the graph, MCP tools, citations, or UI. The required live tool-call and failure-path checks pass with the new model.
- A question about a failing workload combines current tool evidence and relevant runbook guidance with distinct citations.
- Irrelevant or unavailable retrieval does not produce invented document citations or unsupported operational conclusions.
- Re-ingesting a document does not duplicate active chunks; changed document/model versions have a defined replacement/reindex path.
- Restarting application pods preserves chat history and citation metadata; stored observations are clearly labelled historical when reused.
- Provider and retrieval failures remain visible rather than silently producing a healthy conclusion.

Postgres holds operational observations and collection history. It is not a general-purpose replacement for a metrics time-series database.

## S4: bounded investigation, cost questions, and Jev evaluation

Extend the agent from single-source answers to a few bounded investigative workflows. Add cost questions and sanitized event evidence. Evaluate Jev as an optional intent classifier after the core Bedrock path works. Do not add a general security engine or open-ended autonomous exploration.

Work:

1. Use upstream MCP reads for investigation and direct SDK reads for deterministic findings to add sanitized Kubernetes Warning events and deployment/owner relationships for an affected workload. Treat events as recently observed evidence, not a complete audit log. Include Service selector matching in the topology regression scenarios.
2. Permit a bounded sequence of health, event, related-resource, and runbook reads in LangGraph. Set tool-call, iteration, time, and context limits; the model cannot add permissions or run write actions.
3. Add direct-SDK daily AWS Cost Explorer totals/service breakdown over a bounded date range; prefer verified AWS-provided MCP capabilities for exploratory cost questions, without a custom general-purpose wrapper. An explicitly documented agent-internal deterministic calculation/history function may consume normalized results through ordinary code, never masquerading as an upstream MCP capability. Handle pagination and freshness; do arithmetic in code and ground explanations in returned numbers. Persist a small daily cost series if it fits the schema already established.
4. Build two small evidence-backed findings: unavailable replicas and repeated recent restarts. Link each to observations and a runbook; use deterministic code for finding conditions.
5. Implement Jev behind a typed, disabled-by-default classifier interface using the intended Vercel gateway integration. Evaluate classification quality, latency, and failure behavior on a small benchmark. Activate only after the existing geography/retention/minimization requirements are verified: no credentials, identity, cloud tool results, or retrieved context leave through classification. Uncertain or failed classification falls back to the Bedrock workflow. Classification never grants access or performs calculations.

Acceptance:

- “Help me investigate this workload” follows the bounded tool path and distinguishes demonstrated facts from hypotheses and next checks.
- “What did these services cost during this period?” agrees with the equivalent Cost Explorer query and cites source/date/freshness.
- Tool-loop limits, unavailable event sources, stale data, and partial results produce explicit limits.
- The Jev-on/off evaluation records evidence for keeping it enabled or disabled. Disabling Jev preserves the full core product journey.

Broad topology diagrams, EBS/security-group inventory, detailed change detection, and Prometheus integration remain later increments. Do not pull them into this sprint alongside the intelligence work.

## S5: harden what already works

This is an operational reliability baseline for the private alpha. It does not certify general production readiness or HA.

Work:

1. Automate builds, meaningful unit/integration tests, and the Kind smoke journey in CI; release immutable images with pinned dependencies.
2. Add resource requests/limits, health probes, timeouts, bounded retries, collection concurrency limits, and duplicate-job protection.
3. Tighten pod security, IAM, RBAC, network access, and credential renewal; sanitize application logs and avoid raw sensitive event storage.
4. Monitor Vyom itself: per-server MCP discovery/auth/session/latency failures, upstream tool-schema drift, collection and tool failures, request duration, graph steps, model usage/cost, retrieval failures, last success, and storage availability. Avoid raw prompts, answers, and tool payloads in routine telemetry.
5. Back up Postgres and Qdrant outside the cluster and restore into a clean test deployment. Protect backup access, document corpus re-ingestion, and define alpha retention. Native state recovery remains essential.
6. Rehearse release rollback and recovery; run the grounded-answer evaluation suite and deliberate model/MCP/Qdrant failure scenarios. Add streaming and cancellation only after the bounded final-response path works reliably.

Acceptance:

- Clean installation and upgrade both pass the existing Kind/EKS smoke journeys.
- Collector downtime produces an explicit stale indication and bounded recovery.
- Restored Postgres/Qdrant state supports history, citations, and retrieval; the corpus can also be rebuilt from authoritative runbooks.
- A bad release can be rolled back using documented commands.
- The unauthenticated development mode still has no public application entry point.
- Known factual questions pass evidence and arithmetic checks; malicious retrieved instructions and unavailable tools cannot produce unauthorized actions or fabricated citations.

## S6: introduce identity and a small tenant model

Add Keycloak and backend-enforced authorization after the personal product is useful. Keep onboarding operator-managed to bound the work.

Work:

1. Deploy Keycloak with durable state, a consistent realm/client configuration, and working login/logout/refresh.
2. Add JWT verification and users, tenants, and memberships. Resolve active tenant and role from verified identity and server-side membership.
3. Replace the development context resolver; migrate the existing workspace to the owner's initial tenant without losing history.
4. Assign AWS connections, Kubernetes clusters, and namespace/cluster-wide grants to tenants. Do not accept caller-selected authority from headers or tool arguments.
5. Enforce viewer and operator access across the backend, MCP tools, graph checkpoints, cached results, retrieval, document/evidence access, chat sessions/history, and collection jobs. Resolve endpoint and credential scope inside the MCP host; upstream servers are not assumed to understand Vyom tenant headers. Use separately scoped Kubernetes MCP deployments/ServiceAccounts for distinct tenant grant scopes and account-bound AWS credentials; also enforce context on direct SDK paths. Test pooled session isolation, endpoint selection and revocation; user prompts and model arguments cannot override authority.
6. Add audit events for connection/grant changes and denied access. Include Keycloak state in backup/restore procedures. Design credential segregation; bring in Vault here only if supporting additional connection secrets makes it necessary.
7. Test two tenants with distinct fixture accounts, namespaces, and history. Configure HTTPS and authenticated ingress only when the authorization and recovery checks pass.

Acceptance:

- Valid login works; expired, wrong-issuer, wrong-audience, and missing tokens fail.
- Tenant A cannot access B through resource IDs, filters, forged tenant values, tool calls, retrieved chunks, citations, graph/session IDs, caches, background collection, or retained history.
- Namespace revocation takes effect for both fresh and persisted Kubernetes results.
- An ordinary viewer cannot change connections, grants, or trigger privileged operations.
- Development identity mode is disabled for externally accessible deployments.

If the tenant boundary or recovery checks do not fit the final sprint, keep the app private and carry those tasks forward. Do not weaken the acceptance gates to meet the calendar.

## Keep out of the 12-week core

- Azure/GCP provider APIs and AKS/GKE-specific enrollment.
- Multiple remote clusters and automated cross-account onboarding.
- CloudTrail → EventBridge → SQS streaming ingestion and live AWS change guarantees.
- Full Security Hub aggregation, SCA/SBOM, formal compliance, FinOps recommendations, and external alert channels.
- Arbitrary document uploads, generic crawlers, public MCP integrations, and unconstrained autonomous agents. The MCP host and selected upstream integrations, Bedrock/LangGraph chat, curated RAG/Qdrant, and Jev evaluation are in scope above.
- General-purpose Prometheus/log/trace analytics, custom monitoring agents, and Kubernetes cost allocation.
- Multi-region DR, comprehensive HA, public self-signup, subscriptions, and general external beta commitments.

The first three months deliver the intelligence layer progressively: OpenAI-compatible reasoning and live tools in S1, AWS/EKS evidence in S2, Bedrock and curated retrieval in S3, and bounded investigation/classification in S4. Later breadth must build on that working path.

## Fresh project tracking

Use new sprint task IDs such as `S1.1`, `S1.2`, and `S2.1`, with acceptance evidence beside each task. The old B-task tracker is historical scope, not the execution authority for the new application. Previous code-completion statuses do not imply completion in the fresh build.

Start with a small layout: frontend, API/agent with MCP client and direct SDK collectors, tests, deployment chart, documentation, and developer scripts. Add curated corpus/ingestion and database migrations in S3, production infrastructure/recovery definitions in the relevant sprints, and identity integration in S6. Do not pre-create empty services for all future domains.

| New workstream | Delivery |
|---|---|
| Reset, shadcn/ui chat/evidence, OpenAI-compatible model adapter, LangGraph, upstream Kubernetes MCP integration, direct pod view, fresh Vyom containers/chart | S1 |
| AWS-provided MCP integration, direct AWS SDK collection, EKS configuration, basic monitoring in chat and UI | S2 |
| Bedrock reasoning adapter, curated RAG, Qdrant, Bedrock embeddings, new schema/migrations and minimal history | S3 |
| Bounded multi-tool investigation, event evidence, cost queries, Jev evaluation | S4 |
| Reliability, release automation, security baseline, backup/restore | S5 |
| New Keycloak integration, memberships, tenant and namespace enforcement | S6 |
| Optional: NetworkPolicy isolation for the MCP server (verify CNI enforcement) | After S6, optional |
| Streaming cloud ingestion, broad monitoring/security domains, external beta onboarding | Later milestones |

Each sprint closes with a live question-to-evidence-to-answer demonstration, repeatable checks, and documented limits. Create a release tag only when explicitly requested by the owner. A feature that misses its gate moves forward; work is not silently added to the next sprint. Start with one Kubernetes question on Kind through the OpenAI-compatible model + LangGraph + MCP.

See [MCP integration design](docs/MCP_INTEGRATIONS.md) for the deployment/authentication matrix, source evidence and required capability gates. The existing task IDs remain stable; integration estimates must be revisited after upstream compatibility is proven.

## Primary technical references

- Kubernetes resource monitoring: https://kubernetes.io/docs/tasks/debug/debug-cluster/resource-usage-monitoring/ — resource metrics support current CPU/memory; richer metrics require a fuller pipeline.
- EKS IRSA: https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html — IAM roles for service accounts provide scoped AWS credentials for supported SDKs in pods.
- LangChain chat integrations: https://docs.langchain.com/oss/python/integrations/chat — compatible Chat Completions endpoints support basic chat through custom base URLs; additional provider/model capabilities require verification.
- LangChain Bedrock integration: https://docs.langchain.com/oss/python/integrations/chat/bedrock — the Bedrock implementation is separate from the initial compatible API adapter.

Reset evidence (3 October 2026): all existing project files except this constitution were removed from the working tree, including AGENTS.md, implementation, assets, documentation, and deployment files. Only Git metadata and environment-managed read-only directories remain alongside this plan. No backup, archive, commit, tag, or replacement scaffold was created. S1 implementation and its live acceptance gates remain pending.
