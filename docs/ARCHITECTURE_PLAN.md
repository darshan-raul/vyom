# Cloud Cost Compass — Architecture Plan

> Archived design. Superseded by `ARCHITECTURE.md`, `ROADMAP.md`, and `INFERENCE.md`.
> Historical MiniMax settings below are not runtime dependencies; the client was removed on 2026-10-03.

## Implemented Decisions

| Requirement | Decision |
|---|---|
| Data layer | Native cloud SDKs (boto3) — no Steampipe/Powerpipe |
| Dashboard | Streamlit |
| Agent | LangGraph/LangChain + Minimax M2.7 |
| RAG vector DB | Qdrant (separate from pgvector) |
| RAG service | Standalone FastAPI on port 8001 |
| Multi-tenancy auth | SSO/OIDC (Keycloak self-hosted) |
| MCP hosting | FastMCP server on port 8000 |
| Secret store | Vault Agent sidecar (no K8s secret objects) |
| Infra | Kind (local), EKS (cloud), Gateway API (Envoy Gateway) |

---

## Implemented Architecture

```
Browser → Envoy Gateway → Streamlit (8501)
                              │
                         LangGraph Agent
                        ┌──────┴──────┐
                        │             │
              MCP Server (8000)  RAG Service (8001)
              ┌─────────┴──┐         │
         get_costs   get_resources  │
              │             │       ├─→ Qdrant (vectors)
         AWS CE API   boto3         ├─→ Minimax Embed API
              │             │       └─→ PostgreSQL (chat history)

All services: Vault Agent sidecar renders secrets to emptyDir volume
```

---

## Multi-tenancy

- `tenant_id` from OIDC token `sub` claim
- Tenant AWS credentials: `secret/tenants/{tenant_id}/aws.json` in Vault
- Qdrant collection per tenant: `rag-{tenant_id}`
- All DB queries and SDK calls filtered by `tenant_id`

---

## Secrets (Vault Agent)

| Vault Path | Rendered To | Used By |
|---|---|---|
| `secret/minimax/api_key` | `MINIMAX_API_KEY` env var | RAG service, Streamlit |
| `secret/app/encryption_key` | `ENCRYPTION_KEY` env var | MCP server |
| `secret/tenants/{tenant_id}/aws.json` | `/etc/secrets/tenants/{tenant_id}/aws.json` | MCP server |

---

## RAG Service

- **Port**: 8001
- **Endpoints**: `/retrieve`, `/ingest`, `/history`, `/health`
- **Embedding**: Minimax `embo` model, 384 dim, DOT similarity in Qdrant
- **Chunking**: 512-char fixed with 50-char overlap
- **Collection naming**: `rag-{tenant_id}`

---

## MCP Server

- **Port**: 8000
- **Framework**: FastMCP
- **Tools**: `get_costs`, `get_resources`
- **Auth**: Tenant credentials read from `/etc/secrets/tenants/{tenant_id}/aws.json`

---

## K8s Services

| Service | Port | Notes |
|---|---|---|
| vault | 8200 | Dev mode, no persistence |
| keycloak | 8080 | Dev mode |
| postgres | 5432 | No persistence |
| mcp-server | 8000 | FastMCP |
| streamlit | 8501 | Dashboard |
| rag-service | 8001 | FastAPI |
| qdrant | 6333/6334 | gRPC/HTTP |

---

## Phase Status

- **Phase 1** — Done (AWS only, MCP, Streamlit, Vault sidecar)
- **Phase 2** — Done (RAG service, Qdrant, chat history)
- **Phase 3** — Pending (Azure + GCP)
- **Phase 4** — Pending (anomaly alerts, Slack integration)
