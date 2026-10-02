# Vyom — Architecture

> Target architecture, not a claim of deployed capability. Replaces `ARCHITECTURE_PLAN.md` (the historical Streamlit model). Cloud and Kubernetes collection feed one tenant-isolated agent + dashboard; first-release Kubernetes work is tracked in B11.

## Decisions

| Concern | Decision | Alternatives considered |
|---|---|---|
| Data layer | Native cloud SDKs (boto3, azure-mgmt, google-cloud-*) | Steampipe/Powerpipe |
| UI | **Refine + shadcn/ui (Vite + TS)** | Streamlit, Gradio, Next.js, Appsmith, Tooljet |
| Agent | LangGraph/LangChain + Amazon Bedrock in `ap-south-1` | Minimax/external inference |
| Intent classification | Optional actual TypeSafe Jev through Vercel AI Gateway (D34); typed decisions with local escalation | Jev-like interface alone, external reasoning fallback |
| RAG vector DB | Qdrant (separate from pgvector) | pgvector only |
| RAG service | Standalone FastAPI on 8001 | — |
| MCP server topology | Single FastMCP server, namespaced tools | Per-domain / per-cloud servers |
| Multi-tenancy auth | OIDC (Keycloak self-hosted); verified `sub` → server-side user/membership → tenant context | Treating `sub` as the tenant |
| AuthZ | Roles checked in UI **and** MCP tool wrappers | UI-only or MCP-only |
| Secret store | Vault Agent sidecar → `emptyDir` (no K8s Secret objects) | K8s Secret objects |
| Infra | Kind (local/CI), single-region EKS in `ap-south-1` in a dedicated platform AWS account (beta), self-managed stateful workloads, Gateway API (Envoy Gateway), HTTPS under provisional `cc.darshanraul.me` | Docker Compose, shared platform/monitored account, RDS/managed platform data services, multi-region beta, raw endpoint/HTTP beta, Nginx ingress |
| AWS onboarding | Authenticated CLI + pinned OpenTofu; explicit user-run apply | Browser secret entry, CloudFormation-first flow |
| Change ingestion | EventBridge → SQS → EKS worker with IRSA, DLQ, idempotency; daily reconciliation | Polling only, public webhook |
| Kubernetes collection | Separate API list/watch + reconciliation for EKS/AKS/GKE/self-managed; optional authenticated outbound private-cluster collector (B11) | Cloud APIs alone, unrestricted kubeconfig or cluster-wide collection |
| AI data boundary | Allowlisted in-region Bedrock reasoning/embeddings, zero retention, no cross-region inference or invocation-content logs; D34 separately permits minimized request-text classification through Vercel/Jev | Default retention, external reasoning/embedding fallback, model training on tenant content |
| Backup/recovery | Velero → dedicated encrypted S3 backup bucket in `ap-south-1`, EBS snapshots, native Postgres/Qdrant/Vault exports, restore drills | Same-cluster-only backup, Velero-only database restore, RDS |

## Topology

```
Browser
  │ HTTPS
  ▼
Envoy Gateway  ──►  app :8080  (Refine + shadcn/ui, nginx-served SPA + /api reverse proxy)
                       │
                       ├─ /api/mcp/*    → mcp-server :8000
                       ├─ /api/rag/*    → rag-service :8001
                       ├─ /api/alerts/* → alerts-service :8002  (Phase 3)
                       └─ /api/agent/*  → agent endpoint  (SSE to LangGraph)
```

Backend services:

| Service | Port | Phase | Purpose |
|---|---|---|---|
| vault | 8200 | 1 | Secret store (dev mode) |
| keycloak | 8080 | 1 | OIDC issuer; realm `cloud-compass`; roles `viewer`/`operator`/`admin` |
| postgres | 5432 | 1 | History, inventory, findings, SBOM, compliance, alerts |
| qdrant | 6333/6334 | 1 | Vector store (per-tenant collections) |
| mcp-server | 8000 | 1 | FastMCP, all namespaced tools (cost, finops, inventory, security, sca, compliance, alerts, auth) |
| app | 8080 | 1 | Refine + shadcn/ui dashboard; nginx serves static + proxies `/api/*` |
| rag-service | 8001 | 1 | `/retrieve`, `/ingest`, `/history`, `/security_kb`, `/compliance_kb`, `/cve` |
| alerts-service | 8002 | 3 | Rules, channels, recent events |
| cronjobs | — | 2/3 | inventory-snapshot, cve-sync, anomaly-eval, compliance-evidence |
| event-worker | — | AWS beta | Consumes tenant-routed EventBridge events from SQS; updates inventory and security state |

## MCP Tool Surface

Namespaced, single server. Every tool is tenant-scoped and role-checked.

- **auth**: `auth.whoami`
- **cost**: `cost.get_costs`, `cost.get_forecast`
- **finops**: `finops.get_rightsizing`, `finops.get_reservation_coverage`, `finops.get_reservation_utilization`, `finops.get_idle_resources`
- **inventory**: `inventory.list_resources`, `inventory.get_tag_coverage`, `inventory.get_unused_resources`
- **kubernetes (planned B11)**: `kubernetes.list_clusters`, `kubernetes.list_resources`, `kubernetes.get_topology`, `kubernetes.get_health`, `kubernetes.list_events`, `kubernetes.list_findings`
- **security**: `security.list_findings`, `security.get_iam_anomalies`, `security.get_public_assets`, `security.get_encryption_status`
- **sca**: `sca.list_vulnerabilities`, `sca.get_sbom`, `sca.ingest_sbom`, `sca.sync_cve_feed`
- **compliance**: `compliance.list_frameworks`, `compliance.get_control_status`, `compliance.generate_evidence`
- **alerts**: `alerts.list_rules`, `alerts.create_rule`, `alerts.delete_rule`, `alerts.list_events`, `alerts.test_channel`

## Provider Abstraction

```
mcp-server/
  providers/
    base.py        # CloudProvider protocol
    aws.py         # boto3
    azure.py       # azure-mgmt, azure-identity
    gcp.py         # google-cloud-*
    factory.py     # providers_for(tenant_id) -> list[CloudProvider]
```

The factory reads `secret/tenants/{tenant_id}/providers/{aws,azure,gcp}.json` from the rendered Vault volume and instantiates only the providers that have credentials. The onboarding CLI writes only the newly-created least-privilege connector credential; it never retrieves stored credentials.

The provider layout above is planned; current AWS functions are still embedded
in `mcp-server/server.py`. The separate internal Kubernetes implementation now
exists at `mcp-server/connectors/kubernetes/` (B1.9): trusted-context/grant checks
→ bounded API lists → allowlisted records → topology/health/posture. It is not
registered as a public MCP tool. Watch collection, persisted history, onboarding,
private collector and authenticated UI/agent integration remain B11 work. See
[implemented Kubernetes boundaries](KUBERNETES.md).

## Multi-tenancy rules

- Keycloak `sub` identifies a user. The verified request resolves `tenant_id` and role through a server-side membership lookup, never from a request body/header/tool argument.
- Every Postgres query: `WHERE tenant_id = %s`.
- Every Qdrant call: `rag-{tid}`, `kb-{tid}-*`, `cve-{tid}`.
- Every Vault read: `secret/tenants/{tenant_id}/...`.
- MCP server injects `tenant_id` + `role` from the verified token.
- Role checks happen in **both** UI and MCP wrappers.
- Kubernetes access also resolves cluster ownership and permitted namespaces server-side; cluster-wide objects require a separate grant. Models and request arguments cannot grant access.

## AWS + Kubernetes first-release boundary

The first user monitors a personal AWS account from a dedicated EKS platform account. Live AWS and clearly marked simulated AWS connections are planned; Floci and deterministic fixtures cover integration, event, anomaly, and failure tests. The beta targets daily Cost Explorer history, EventBridge-fed CloudTrail management changes, Security Hub findings, and the initial inventory set. The owner added Kubernetes inventory/topology, health/events, and configuration posture across EKS/AKS/GKE/self-managed clusters to the first release. This adds B11 acceptance work and requires re-estimating the original AWS-only timebox.

Cloud connectors collect infrastructure/billing; a separate Kubernetes connector collects authorized API objects/status/events and normalizes evidence into tenant-scoped Postgres records and relationships. Private clusters can use the planned authenticated outbound collector. Cloud links are evidence-based and may be unknown for self-managed clusters or unavailable GCP/Azure cloud adapters. Historical monitoring, Kubernetes cost allocation/rightsizing, full logs/traces and formal controls are later stages. Namespace costs must reconcile to infrastructure charges without counting nodes twice. See [Kubernetes scope and collection path](KUBERNETES.md).

Reasoning/embeddings target `ap-south-1` Bedrock with zero retention, no cross-region inference and no invocation-content logging. Optional Jev classification through Vercel is the separate D34 external-processing exception, gated by B8.6; it does not receive tool results or retrieved context. Tenant authorization, lifecycle enforcement, authenticated LangGraph integration and live data-handling evidence remain implementation gates. The release is read-only; SCA, formal compliance, advanced FinOps, Slack automation and GCP/Azure cloud-provider parity remain deferred.

## RAG

- Embedding: an in-region Bedrock model compatible with the zero-retention policy; collection dimension is versioned with the selected model.
- Chunking: 512-char fixed, 50-char overlap.
- Collections: `rag-{tid}`, `kb-{tid}-security`, `kb-{tid}-compliance`, `cve-{tid}`.
- RAG endpoints: `/retrieve`, `/ingest`, `/history`, `/security_kb`, `/compliance_kb`, `/cve`.

The 2026-10-03 adapter refactor uses model-versioned `rag-{tid}-v1-{spec_hash}`
collections for Bedrock. Legacy vectors require explicit re-embedding; they are
never queried as a fallback. Runtime configuration and the intended LangGraph
classification flow are documented in [INFERENCE.md](INFERENCE.md). Adapters are
implemented; the authenticated agent runtime and live migration remain pending.

## Phases

1. **Foundation** — auth, cost + inventory across AWS/Azure/GCP, RAG chat, UI scaffold.
2. **Security + FinOps** — CSPM, IAM drift, rightsizing, reservations; security/FinOps pages.
3. **SCA + Compliance + Alerts** — SBOM, CVE/KEV, framework packs, anomaly detection, Slack.

Full tracker in `AGENTS.md`.
