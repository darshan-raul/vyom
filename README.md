# Vyom

**Grounded intelligence for the modern cloud.**

Tenant-isolated cloud operations. One explainable cockpit for spend, posture, and risk across AWS and Kubernetes.

Vyom turns scattered cloud telemetry into deterministic, RAG-grounded insight—orchestrated by LangGraph agents and secure MCP tooling.

> Formerly **Cloud Compass**, originally **Cloud Cost Compass**. The first-release scope now includes AWS and Kubernetes visibility, health, and configuration posture; cluster collection remains pending implementation. Historical metrics, Kubernetes cost allocation/rightsizing, and cloud billing/security parity for GCP and Azure follow later. See [Kubernetes scope](docs/KUBERNETES.md) and the [execution tracker](docs/BETA_EXECUTION_PLAN.md).

## What it does

Vyom is designed to give a single tenant-isolated view of:

| Domain | Question it answers |
|---|---|
| **Cost** | Where is money being spent, and is it trending up? |
| **FinOps** | Where can we save? (rightsizing, reservations, idle resources) |
| **Inventory** | What do we actually have, and is it tagged? |
| **Security** | Where are we exposed? (CSPM, IAM drift, public assets, encryption) |
| **SCA** | Are our workloads vulnerable? (SBOM, CVE, EPSS, KEV) |
| **Compliance** | Are we audit-ready? (CIS, SOC2, auto-evidence) |

The target architecture exposes these domains through tenant-scoped MCP tools and a single LangGraph agent. The runtime agent and most domain integrations remain pending in the execution tracker.

## Target capabilities

- **Multi-Cloud Parity**: AWS (boto3), Azure (azure-mgmt / azure-identity), GCP (google-cloud-*) via a single `CloudProvider` protocol.
- **Kubernetes Coverage**: Separate read-only API collection for EKS, AKS, GKE, and self-managed clusters, with permitted-namespace and separate cluster-wide grants; inventory/topology, health/events, and configuration posture (B11).
- **Natural Language Operations**: LangGraph agent + in-region Amazon Bedrock inference selects and chains tools across all six domains.
- **MCP Tool Server**: One FastMCP server (port 8000), namespaced tools (`cost.*`, `finops.*`, `inventory.*`, `security.*`, `sca.*`, `compliance.*`, `alerts.*`).
- **RAG-Powered Insights**: Qdrant vector store + an in-region Bedrock embedding model; separate collections for chat docs, security KB, compliance KB, and CVE corpus.
- **Multi-Tenant Dashboard**: **Refine + shadcn/ui (React + Vite + TypeScript)**, OIDC SSO (Keycloak), per-tenant data isolation enforced in DB layer, Qdrant collections, Vault paths, and MCP tool wrappers.
- **Streaming Chat**: Vercel AI SDK hits the LangGraph agent over SSE; tool calls rendered inline with citations.
- **Role-Based Access**: `viewer` / `operator` / `admin` enforced in both UI route guards and MCP tool wrappers (defense in depth).
- **Vault Agent Sidecars**: All app secrets (API keys, cloud credentials, Slack webhooks) rendered from HashiCorp Vault at runtime to `emptyDir` volumes. **No Kubernetes Secret objects used for application secrets.**

## Architecture

The immediate release is a read-only **AWS + Kubernetes personal beta**: daily AWS cost, infrastructure changes, Security Hub/direct checks, cluster/workload inventory, health/events, configuration posture, and grounded chat. It runs on Kind locally and EKS in a separate platform AWS account. Kubernetes has its own connector for EKS, AKS, GKE, and self-managed clusters; cloud billing/provider parity still follows AWS → GCP → Azure. The expanded scope needs a revised delivery estimate. See [`docs/ROADMAP.md`](docs/ROADMAP.md) and [Kubernetes architecture](docs/KUBERNETES.md).

The [September infrastructure diagram](docs/diagrams/aws-beta-infrastructure.html) is a historical snapshot predating the Vyom rename and Kubernetes workstream.

```
                    ┌─────────────────────────┐
                    │  Browser (end user)     │
                    └────────────┬────────────┘
                                 │ HTTPS
                    ┌────────────▼────────────┐
                    │   Envoy Gateway         │  Gateway API
                    │   (TLS, routing)        │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Refine + shadcn/ui    │  :8080 (nginx) → Vite static + reverse proxy
                    │   (React, Vite, TS)     │  /api/* → backend services
                    └─┬───────────┬─────────┬─┘
                      │           │         │
              ┌───────▼──┐  ┌─────▼────┐  ┌─▼──────────┐
              │   MCP    │  │   RAG    │  │  Alerts    │
              │  Server  │  │ Service  │  │  Service   │
              │  :8000   │  │  :8001   │  │  :8002     │
              └────┬─────┘  └────┬─────┘  └─────┬──────┘
                   │             │              │
       ┌───────────┼──┐    ┌─────┼─────┐        │
       │           │  │    │     │     │        │
   ┌───▼──┐  ┌─────▼┐ │  ┌─▼──┐ ┌▼───┐ │   ┌────▼────┐
   │ AWS  │  │Azure │ │  │Qdr.│ │Postg│ │   │ Slack   │
   │ SDK  │  │ SDK  │ │  │6334│ │5432│ │   │ Webhook │
   └──────┘  └──────┘ │  └────┘ └────┘ │   └─────────┘
               ┌──────▼┐               │
               │ GCP   │               │
               │ SDK   │               │
               └───────┘               │
        All pods: Vault Agent sidecar ◄┘
        renders secrets to emptyDir vol
        (no K8s Secret objects for app secrets)
```

## Repository Structure

```
cloud-cost-compass/                  (repo name preserved; product is Vyom)
├── README.md
├── AGENTS.md                         # phase plan + agent invocation tracker
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SECURITY.md
│   └── RUNBOOKS.md
├── app/                              # Refine + shadcn/ui dashboard (Vite + TS)
│   ├── Dockerfile                    # multi-stage: node build → nginx serve
│   ├── nginx.conf                    # SPA + /api reverse proxy
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── components.json               # shadcn config
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx                   # Refine + Router + AuthProvider
│   │   ├── auth/                     # Keycloak OIDC + role guards
│   │   ├── providers/                # refine data providers → MCP / RAG / Alerts
│   │   ├── pages/                    # overview, costs, finops, inventory, security, sca, compliance, alerts, chat, settings
│   │   ├── components/               # shadcn/ui + domain widgets
│   │   ├── lib/                      # api client, role helpers, formatters
│   │   └── styles/                   # tailwind globals
│   └── public/
├── mcp-server/                       # FastMCP server, namespaced tools
│   ├── server.py
│   ├── providers/                    # base, aws, azure, gcp, factory
│   ├── tools/                        # cost, finops, inventory, security, sca, compliance
│   └── Dockerfile
├── rag-service/                      # FastAPI
│   ├── server.py
│   ├── routers/                      # retrieve, ingest, history, compliance_kb, cve
│   ├── embed/                        # Bedrock RAG facade + provider-neutral chunking
│   ├── inference/                    # Bedrock adapters + optional Jev via Vercel AI Gateway
│   ├── qdrant/                       # Qdrant client
│   └── Dockerfile
├── alerts-service/                   # Phase 3
├── compliance/                       # YAML framework packs (committed)
├── migrations/                       # 9 phase-stamped SQL files
├── infra/
│   ├── k8s/                          # 00..10 manifests + Gateway API
│   └── kind/
└── scripts/                          # setup-kind, deploy-eks, seed-vault, bootstrap-tenant
```

## Setup

### Local Kind

```bash
./scripts/setup-kind.sh
```

### EKS

```bash
export REGISTRY=your-registry.example.com
./scripts/deploy-eks.sh
```

### Build images

```bash
docker build -t cloud-cost-compass/app:latest -f app/Dockerfile app/
docker build -t cloud-cost-compass/mcp-server:latest -f mcp-server/Dockerfile mcp-server/
docker build -t cloud-cost-compass/rag-service:latest -f rag-service/Dockerfile rag-service/
```

### App (local dev)

```bash
cd app
npm install
npm run dev      # vite dev server on :5173, proxies /api/* to localhost:8000/8001/8002
```

### Kind image load

```bash
kind load docker-image cloud-cost-compass/app:latest --name cloud-cost-compass
kind load docker-image cloud-cost-compass/mcp-server:latest --name cloud-cost-compass
kind load docker-image cloud-cost-compass/rag-service:latest --name cloud-cost-compass
kind load docker-image qdrant/qdrant:v1.7.4 --name cloud-cost-compass
kind load docker-image hashicorp/vault:1.16 --name cloud-cost-compass
```

## Beta onboarding and environments

- **Kind** is the required local and CI target; **EKS** in a dedicated Vyom AWS account is the hosted beta target.
- A Keycloak-authenticated `vyom` CLI will generate pinned OpenTofu onboarding configuration and validate a connection. Applying infrastructure is always an explicit user action.
- The CLI sends the newly-created, least-privilege AWS read-only connector secret to tenant Vault once. It does not retrieve stored AWS credentials.
- Live connections are complemented by clearly labelled **Simulated AWS** connections backed by Floci and deterministic fixtures.
- CloudTrail management events and Security Hub findings flow through EventBridge → SQS → an EKS worker. Daily snapshots reconcile event delivery; cost is daily and never described as real-time.
- Bedrock inference is in-region in `ap-south-1`, uses zero retention, disables invocation-content logging, and never uses tenant content for model training. The application still minimizes/redacts prompts and enforces its own retention/deletion policy.
- Optional Jev intent classification uses **Vercel AI Gateway** under D34's separate external-processing boundary. It is disabled by default and accepts minimized request text only. Adapter code exists; authenticated LangGraph integration and live policy/model evaluation remain pending. See [inference configuration and vector transition](docs/INFERENCE.md).

## Vault Secret Paths

| Path | Rendered As | Used By |
|---|---|---|
| AWS IRSA for Bedrock | Short-lived workload identity | Bedrock adapters in agent/RAG services |
| `secret/agent/ai_gateway_api_key` (planned B8.6) | `/etc/secrets/ai-gateway-api-key` | Optional backend Jev classifier; never the browser |
| `secret/app/encryption_key` | `ENCRYPTION_KEY` env var | MCP server |
| `secret/tenants/{tenant_id}/providers/aws.json` | `/etc/secrets/tenants/{tenant_id}/providers/aws.json` | MCP server |
| `secret/tenants/{tenant_id}/providers/azure.json` | `/etc/secrets/tenants/{tenant_id}/providers/azure.json` | MCP server |
| `secret/tenants/{tenant_id}/providers/gcp.json` | `/etc/secrets/tenants/{tenant_id}/providers/gcp.json` | MCP server |
| `secret/tenants/{tenant_id}/alerts/slack_webhook` | `/etc/secrets/tenants/{tenant_id}/alerts/slack_webhook` | Alerts service (Phase 3) |

## Keycloak

Keycloak at `http://keycloak:8080/realms/cloud-compass`. Realm: `cloud-compass`. Realm roles: `viewer`, `operator`, `admin` (mirrored into `user_roles` table).

The Refine app uses an OIDC code-flow client (configured via `VITE_KEYCLOAK_*` env vars) and reads roles from the JWT for client-side route guards. The MCP server re-validates the JWT and re-checks roles for server-side enforcement (D2).

## MCP Tools (per phase)

### Phase 1
`auth.whoami`, `cost.get_costs`, `cost.get_forecast`, `inventory.list_resources`, `inventory.get_tag_coverage`, `inventory.get_unused_resources`

### Phase 2
`finops.get_rightsizing`, `finops.get_reservation_coverage`, `finops.get_reservation_utilization`, `finops.get_idle_resources`, `security.list_findings`, `security.get_iam_anomalies`, `security.get_public_assets`, `security.get_encryption_status`

### Phase 3
`sca.list_vulnerabilities`, `sca.get_sbom`, `sca.ingest_sbom`, `sca.sync_cve_feed`, `compliance.list_frameworks`, `compliance.get_control_status`, `compliance.generate_evidence`, `alerts.list_rules`, `alerts.create_rule`, `alerts.delete_rule`, `alerts.list_events`, `alerts.test_channel`

## RAG Service Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/retrieve` | POST | Semantic search (embed query → Qdrant → chunk texts) |
| `/ingest` | POST | Ingest document (chunk → embed → Qdrant + Postgres) |
| `/history` | GET/POST | Chat history CRUD |
| `/security_kb` | POST | Security playbook / CIS control retrieval |
| `/compliance_kb` | POST | Policy text / control mapping retrieval |
| `/cve` | POST | CVE corpus retrieval filtered to tenant stack |
| `/health` | GET | Liveness |

## Qdrant Collections

| Collection | Purpose |
|---|---|
| `rag-{tenant_id}` | Chat-time doc retrieval (uploads, scraped cost docs) |
| `kb-{tenant_id}-security` | Security playbooks, CIS controls, provider hardening |
| `kb-{tenant_id}-compliance` | Policy text, control mappings |
| `cve-{tenant_id}` | Synced CVE corpus (NVD + EPSS + KEV), filtered to tenant PURLs |

Collections use a versioned dimension and embedding model selected from in-region Bedrock models under the zero-retention policy; migrations prevent mixing vectors from incompatible models.

## UI Stack (locked)

- **Framework**: [Refine](https://refine.dev) (React, headless on K8s)
- **Component library**: [shadcn/ui](https://ui.shadcn.com) (Radix + Tailwind, copy-paste components)
- **Build**: Vite + TypeScript
- **Data**: Refine data providers wrapping MCP / RAG / Alerts REST endpoints
- **Chat**: Vercel AI SDK `useChat` over SSE to a LangGraph agent endpoint
- **Auth**: Refine auth provider against Keycloak OIDC (code flow, PKCE)
- **Tables**: TanStack Table (via Refine `useTable`) for findings, SBOM, control matrices
- **Charts**: Recharts for cost trends, severity donuts, KEV exposure
- **Serve**: nginx (multi-stage Docker build, SPA routing + `/api/*` reverse proxy)

## Multi-Tenancy

- AuthN: OIDC via self-hosted Keycloak; `sub` identifies the user, then server-side memberships resolve the active tenant.
- AuthZ: membership roles (`viewer`, `operator`, `admin`) are enforced in UI and MCP tool wrappers.
- Per-tenant cloud credentials stored in Vault under `secret/tenants/{tenant_id}/providers/`.
- Qdrant collection per tenant; all DB queries and SDK calls filtered by `tenant_id`.
- Encrypted at rest in Postgres via `ENCRYPTION_KEY` (envelope encryption in a follow-up).

## K8s Deploy Order

Files prefixed to enforce ordering: `00-namespace.yaml` → `00-secrets-bootstrap.yaml` → `00-vault.yaml` → `00-1-keycloak.yaml` → `01-postgres.yaml` → `02-mcp-server.yaml` → `03-app.yaml` → `04-gateway.yaml` → `05-migrations.yaml` → `06-rag-service.yaml` → `07-qdrant.yaml` → `08-alerts-service.yaml` (P3) → `09-cronjobs.yaml` (P3) → `10-ingress-tls.yaml`. Apply the whole directory.

## Gateway API

Envoy Gateway handles ingress on Kind. `04-gateway.yaml` creates a Gateway and HTTPRoute routing `/` to the Refine app (8080). The Refine app's nginx reverse-proxies `/api/mcp/*`, `/api/rag/*`, `/api/alerts/*` to the in-cluster backend services. Backend services are ClusterIP-only.

## No test/lint/build scripts

Pure IaC + Docker. No npm scripts, test suites, or lint commands.
