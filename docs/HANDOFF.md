# Current handoff

Updated: 2026-10-03. Latest session: [2026-10-03-02](sessions/2026-10-03-02.md).

## Current state

Planning only. Owner-approved MCP revision is integrated into constitution, existing 38-task plan, responsibilities, deployment/auth design and diagrams. Vyom is the MCP host/client; Kubernetes uses a pinned upstream in-cluster server, AWS exploration uses AWS-managed/provided capabilities, and deterministic collection/persistence uses normal SDKs/APIs. No runtime scaffold exists. Old tracked deletions remain intentional.

The six-sprint sequence is preserved: real local agent in S1; EKS/AWS S2; Bedrock/RAG/history S3; bounded investigations/cost S4; reliability S5; Keycloak/tenancy S6. Do not restore the prior FastMCP server design or route database/dashboard work through MCP. A CLI and additional MCP domains are future options, not new core deliverables.

## Next implementation task

**S1.1 — fresh development scaffold**, when implementation is requested. Inspect local tooling and official dependency docs; create only frontend, FastAPI and an existing-SDK MCP client module plus minimal health/build checks. The current user request expressly authorizes plan updates only.

S1.2 defines host connection/policy/evidence contracts and private upstream transport authentication. S1.3 deploys and pins containers/kubernetes-mcp-server inside Kind, verifies its ServiceAccount/RBAC/read-only/output behavior (NetworkPolicy is optional, end of roadmap). S1.6 builds the independent direct-SDK pod view, deliberately after the MCP-backed agent path (S1.5) works end to end. No Vyom MCP server entrypoint is planned.

## Inputs and risks

- Initial model endpoint/key provisioning before S1.5; no credentials in chat.
- Upstream release, safe result projection and auth mode before S1.3 acceptance.
- AWS endpoint region/data handling, workload credentials and required live tool coverage before S2.1–S2.2; do not assume an ap-south-1 MCP endpoint.
- Re-estimate integration work once compatibility is known; keep scope and existing gates explicit.

## Verification / external effects

Documentation checker results are in the latest session. The Archify delivery wrapper failure is only a note in docs/diagrams/README.md. No application code, manifests, live MCP connections, deployed resources, application processes, commits, tags or pushes were created. Web sources verify upstream design inputs only, not runtime acceptance.
