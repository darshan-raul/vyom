# Vyom — Runbooks

## Local dev

```bash
./scripts/setup-kind.sh
# App:    http://localhost:8080
# Keycloak realm: cloud-compass
```

## UI swap: Streamlit → Refine + shadcn/ui

Replaced the Streamlit dashboard (F1.6) with a Refine + shadcn/ui SPA served by nginx. Why:

- Native OIDC code-flow + PKCE for Keycloak (`keycloak-js` + Refine `authProvider`).
- Data-heavy tables (findings, SBOM, control matrix) need TanStack Table, not `st.dataframe`.
- Streaming chat over SSE via Vercel AI SDK `useChat`, not a one-shot `httpx.post` + `st.markdown`.
- Role-based route guards (`AuthGuard`, `RoleGuard`) mirror server-side MCP role checks (D2).
- Static SPA + nginx reverse proxy for `/api/*` is a small, well-understood K8s unit.

Files added/touched:

- `app/package.json`, `tsconfig.json`, `vite.config.ts`, `tailwind.config.ts`, `postcss.config.js`, `components.json`
- `app/index.html`, `app/public/favicon.svg`, `app/.env.example`
- `app/Dockerfile` (multi-stage node → nginx:alpine), `app/nginx.conf`
- `app/src/main.tsx`, `app/src/App.tsx`
- `app/src/styles/globals.css`
- `app/src/lib/{utils,roles,api}.ts`
- `app/src/auth/{keycloak,authProvider,guards,useSession,session}.{ts,tsx}`
- `app/src/providers/dataProvider.ts`
- `app/src/components/ui/*` (shadcn primitives)
- `app/src/components/layout/AppLayout.tsx`
- `app/src/pages/{overview,costs,finops,inventory,security,sca,compliance,alerts,chat,settings,login}.tsx`
- `infra/k8s/03-app.yaml` (replaces `03-streamlit.yaml`)
- `infra/k8s/04-gateway.yaml` (routed to `app:8080`)
- `scripts/{setup-kind,deploy-eks}.sh` (image + label updates)

Alternatives considered (recorded in `AGENTS.md` D11): Streamlit, Gradio, Next.js, Appsmith, Tooljet.

## Adding a backend service

1. Add K8s manifest under `infra/k8s/0X-*.yaml` with a Vault Agent sidecar.
2. Add the service to `app/nginx.conf` if it needs to be reachable from the UI.
3. If the service has MCP tools, add them under `mcp-server/tools/<domain>.py` and register in `server.py`.
4. Wire the data provider client in `app/src/providers/dataProvider.ts`.

## Adding a new domain

1. Create `migrations/0XX_<domain>.sql`.
2. Add `<domain>/*.py` provider methods.
3. Add `mcp-server/tools/<domain>.py` (tools named `<domain>.<verb>`).
4. Add a Refine page under `app/src/pages/<domain>.tsx` and a nav entry in `AppLayout.tsx`.
5. Add a RAG collection (if KB-backed) and a router in `rag-service/`.

## Updating an agent-tracked task

Append a row to the **Agent Invocation Tracker** table in `AGENTS.md` with the timestamp, item, status delta, and one-line summary.
