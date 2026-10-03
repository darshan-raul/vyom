# MCP integration design

Owner-approved planning revision, 2026-10-03. This elaborates the [constitution](../vyom-12-week-sprint-plan.md); it does not implement or deploy anything. All S1–S6 application tasks remain pending. Existing sprint order and scope are preserved.

## Responsibility boundary

| Component / path | Vyom responsibility | Integration / protocol | Starts |
|---|---|---|---|
| UI; future CLI | Present evidence; call backend; no model/provider credentials | Normal HTTP APIs, OIDC only S6 | UI S1; CLI not newly scheduled |
| Backend + LangGraph | Identity/context, authorization, orchestration, answer/citation validation | Ordinary Python modules/APIs | S1 |
| MCP client/host | Register endpoints, negotiate/discover, filter tools, bind credentials, validate arguments, normalize results, bound calls and close sessions | Existing MCP client library; no new server protocol | S1 |
| Kubernetes MCP | Deploy/configure/upgrade existing upstream server; scoped provider identity | Preferred `containers/kubernetes-mcp-server` in target cluster → Kubernetes API | S1 Kind; S2 EKS |
| AWS MCP | Connect to AWS-managed MCP / suitable AWS-provided capabilities; prove resource investigation support | Authenticated remote MCP; supported AWS signing/proxy if needed | S2 |
| Deterministic collection | Inventory, dashboards, scheduled sync, large pulls, pagination, arithmetic | Direct Kubernetes/AWS SDKs/APIs where simpler | K8s S1; AWS S2; jobs S3 |
| Application state / RAG | Scoped persistence, retrieval, migrations and embeddings | Postgres/Qdrant/model libraries/APIs; no MCP hop | S3 |
| Additional MCP domains | Later registered connections with capability/security review | GitHub, Terraform/IaC, docs, cost/FinOps and others | Later, not extra core deliverables |

The separation is by purpose, not programming language. A deterministic function may be invoked by the agent as normal application code without publishing a new MCP server. Prefer MCP for exploration; label any direct-data/history/calculation path honestly. MCP availability must not become a dependency for unrelated inventory or persistence.

## Client contract and evidence

A registered connection contains a stable server ID, endpoint/transport, pinned client/upstream version where applicable, supported protocol/capability expectations, authentication reference, permitted tool/schema mapping, resource scope, budgets and health state. Do not build a plugin marketplace or generic distributed gateway. Start with one configured Kubernetes endpoint; add the AWS endpoint in S2.

The host derives account/cluster/namespace authority from server context, then intersects proposed tool arguments with that authority. Discovery does not auto-enable newly advertised tools. Use server-qualified names, schema snapshots and explicit enablement. Reject unregistered destinations, arbitrary credential/profile selection, executable snippets, shell/exec, mutations and unrestricted general resource reads. A generic upstream operation tool needs operation-level validation plus IAM/RBAC, not just a tool-name allowlist. Unsupported safe narrowing is a blocked capability, not a reason to broaden access.

Normalize direct and MCP results to workspace/connection/source IDs, account/region or cluster UID/namespace/resource UID, source/collection time, pagination/coverage, partial errors and evidence IDs. Record upstream server/tool identity separately from direct-SDK provenance. Do not invent source timestamps when upstream supplies none. Minimize results before model context, UI, persistence and telemetry; preserve unsupported/partial/unavailable outcomes. Cross-path tests compare equivalent observations within collection timing limits, not exact byte equality.

Kubernetes RBAC controls objects/verbs, not individual pod fields. Even a read-only pod response can contain literal environment values or sensitive annotations. Do not equate `get pods` with safe model output: verify upstream projection and host minimization, avoid raw-object tools where unnecessary, and test sensitive-field removal before exposure. Trusted API processing may encounter raw fields; they must not be forwarded, persisted or logged. Secret objects, pod logs and exec are not part of the initial authorized capability set.

## Kubernetes deployment contract

These are planned requirements, not copied default chart values. Pin an upstream release and inspect its documentation/config/schema at implementation time. If the preferred implementation cannot meet a gate, evaluate another existing implementation with recorded evidence; do not build our own production protocol server.

| Resource / concern | KIND S1 | EKS S2 and later acceptance |
|---|---|---|
| Deployment | Pinned upstream image/digest, one replica sufficient, resource limits, health/readiness, restricted container security context | Same tested version; explicit controlled upgrade/rollback; no `latest` |
| Transport / Service | Prefer supported Streamable HTTP with internal ClusterIP Service; endpoint authentication and TLS or existing authenticated proxy | Same private transport; no public MCP Ingress/LoadBalancer; verify unauthorized client denial |
| Kubernetes identity | Dedicated upstream ServiceAccount, in-cluster config/projected token; no developer-admin kubeconfig | Same identity model; validate token rotation; do not confuse AWS workload IAM with Kubernetes RBAC |
| Role / binding | Demo-namespace Role/RoleBinding for required read verbs/resources only; no wildcard/admin | Add specific workloads/metrics/events when sprint needs them; separate explicit cluster-wide node grant |
| Tool configuration | Explicit read-only, minimal allowlisted tools; no exec, mutation, Secret/raw-log/config-export capability | Upstream upgrade must not re-enable tools or widen resources; tests enforce effective denial |
| Backend identity | Separate deterministic collector ServiceAccount with same intended namespace scope | Separate IAM permissions for deterministic AWS collector and agent AWS connection where feasible |
| Config / secrets | Nonsecret config via mounted config; private runtime credentials/certificates; projected service tokens | Renew/rotate credential material; no credential in Git, image, frontend, logs or MCP tool parameters |
| Network exposure | ClusterIP only, no public exposure; endpoint authentication is the control. NetworkPolicy restricting ingress/egress is optional end-of-roadmap hardening | Endpoint authentication; metrics/health exposure restricted separately |
| Observability | Server/connection health, call count/latency/errors and sanitized logs; no raw content | Correlated server/tool/outcome metadata, auth failure and credential-expiry alerts/diagnostics; expand in S5 |
| Local development | Actual MCP server runs inside Kind; UI via localhost port-forward; optional backend dev connection through localhost-only forwarding | EKS uses internal Service DNS, workload credentials and private app access until S6 |

Optional, end of roadmap: if NetworkPolicy is added, verify the CNI actually enforces it; policy YAML alone is not evidence. Until then make no network-isolation claim. Do not expose a raw MCP port that bypasses the authenticated proxy. Authentication at the MCP endpoint and authentication to the Kubernetes API are separate: configure the latter to always use the scoped ServiceAccount, not a client token accidentally passed through by an upstream default. No Keycloak is needed to establish workload-to-workload authentication in S1.

## AWS integration gate

S2.1 selects the actual managed endpoint or appropriate AWS-provided capability, confirms access and required read operations, and records its endpoint region, target resource region, authentication, data handling, quotas, dependency/version and cost assumptions. The platform remains in `ap-south-1`; this does not imply that every external AWS MCP endpoint is hosted there. If geography or coverage is incompatible, keep the integration gate open and record the supported alternative/retry decision. Do not claim SDK inventory proves AWS MCP integration.

Prefer temporary workload IAM credentials with a supported SigV4 integration for unattended EKS use; an AWS-provided signing proxy is a client-side transport helper, not a Vyom AWS MCP server. Validate the actual client/proxy credential-provider chain and renewal with the selected IRSA role. OAuth is an available alternative only if its unattended flow, scope and lifecycle are verified; a developer's interactive sign-in is not a production workload design. Kind does not require AWS for S1.

IAM must limit underlying AWS actions, accounts and regions as applicable, including safe handling of global APIs. Do not use administrator policies or assume a “read-only” tool label enforces account scope. Disable script execution/mutation operations; narrow generic tools at the host. Unsupported controls leave that capability disabled. Read-only AWS operations can still return sensitive content, so capability selection and output minimization apply here too.

## Identity, tenancy and revocation

- S1–S5: fixed operator context controls endpoint, account, cluster, namespace and allowed capabilities. User filters cannot widen it. Credentials remain out of model inputs.
- S6: verified Keycloak subject → membership/role → connection/grants → selected endpoint plus scoped provider credential. No arbitrary tenant header is interpreted as upstream authorization.
- For the initial two-tenant gate, use separate Kubernetes MCP deployments/ServiceAccounts per distinct tenant grant scope. A shared broad ServiceAccount does not become tenant-safe because the host adds a tenant ID. Same-cluster namespaces may still be used for the test; no remote enrollment is implied.
- AWS role/session selection is server-resolved and account-bound; cache/pool keys include authorized connection/credential/grant identity. Do not share mutable sessions between tenants. Avoid process-global credential/profile switching per request.
- Revocation invalidates MCP sessions and cached authority, reconciles downstream permissions, blocks calls while stale state remains, and reauthorizes stored evidence. Deterministic collectors/jobs use equivalent scope constraints.
- All current sprints remain read-only. Additional permissions, especially writes, require a future explicit use case, approval policy, audit/rollback design and denial tests. Educational MCP servers, if requested, remain outside production dependencies and sprint acceptance.

## Source checks and implementation-time verification

Checked against primary sources on 2026-10-03. These are observations about upstream documentation, not evidence that Vyom has connected successfully. Avoid pinning a development branch or assuming future docs match the chosen release.

| Primary source | Verified observation / implication |
|---|---|
| [Kubernetes MCP upstream](https://github.com/containers/kubernetes-mcp-server) | Existing native Kubernetes API integration is available; adopt it rather than implementing another protocol server. |
| [Upstream configuration reference](https://github.com/containers/kubernetes-mcp-server/blob/main/docs/configuration.md) | Documents Streamable HTTP, read-only/tool filtering, in-cluster configuration, TLS and distinct cluster-auth modes. Defaults and token passthrough require explicit review; pin and test a release. |
| [Upstream Helm chart](https://github.com/containers/kubernetes-mcp-server/blob/main/charts/kubernetes-mcp-server/README.md) | Deployment packaging exists. Review actual rendered permissions and exposure; do not treat defaults as Vyom's policy. |
| [AWS MCP setup](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/getting-started-aws-mcp-server.html) | Documents remote connections and SigV4 proxy/OAuth options; endpoint region and resource-operation region are distinct. |
| [AWS MCP endpoints](https://docs.aws.amazon.com/general/latest/gr/aws-mcp.html) | Lists the managed endpoint in `us-east-1` at review time; do not invent an `ap-south-1` endpoint. Recheck for S2. |
| [AWS MCP IAM](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/security_iam_service-with-iam.html) | Current docs describe downstream IAM authorization and temporary credentials. Preview-era MCP-specific IAM actions are deprecated; verify current policies rather than copying old examples. |

Upstream features and endpoint availability can change. S1/S2 evidence must capture selected versions and actual tool/schema/auth tests; current web research cannot close those implementation gates.
