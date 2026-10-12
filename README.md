<p align="center">
  <img src="assets/branding/vyom-logo.png" width="128" alt="Vyom logo" />
</p>

<h1 align="center">Vyom</h1>

A progressively built AWS + Kubernetes intelligence cockpit: ask a question, inspect live read-only evidence, and understand the answer.

**Current state:** S1.1 and S1.9 are done: a fresh [frontend](frontend/) and [backend](backend/) scaffold with a health endpoint, an MCP client module and a telemetry baseline, plus a pinned Prometheus/Grafana, Loki, Tempo and Alloy stack that installs on Kind. There is no chat, Kubernetes view, model, upstream MCP server or application chart yet; the rest of S1 and every sprint gate remain open. See [Run the scaffold](#run-the-scaffold) and [Run the observability stack on Kind](#run-the-observability-stack-on-kind). A separate [two-Kind-cluster chat POC](poc/kind-chat/README.md) exists outside the roadmap and gives no S1–S6 completion credit.

## Planned service overview

The planned deployment runs on Kind in S1 and EKS in S2. Service groups distinguish application workloads, cluster integration, persistent state, observability and external dependencies. Sprint labels show when each component enters the plan.

![Vyom planned deployment architecture: application workloads, cluster integration, state and RAG, observability and external providers](docs/diagrams/readme-architecture.svg)

[Open full-size diagram](docs/diagrams/readme-architecture.svg) · [Detailed architecture and request paths](docs/ARCHITECTURE.md) · [Observability collection topology](docs/OBSERVABILITY.md#collection-topology)

FastAPI, LangGraph, the MCP host and deterministic collectors share one backend workload. Chat explores through upstream MCP integrations; inventory uses direct SDKs. Postgres and Qdrant use normal clients, while jobs reuse backend libraries. The model provider is explicitly configured, with Bedrock introduced in S3. **RAG starts in S3 inside the backend:** jobs ingest curated runbooks using Bedrock embeddings, Qdrant retrieves relevant sections, and LangGraph combines that guidance with live evidence using distinct citations.

The diagram shows primary connections; placement identifies deployment ownership. Observability starts in S1, with bounded exports and private Grafana access. Access stays private through localhost port-forwarding before S6; backend membership/grant policy supplies authority after Keycloak verifies identity.

| Workload / dependency | Responsibility | Starts |
|---|---|---|
| Frontend Deployment | Chat, evidence panels and deterministic resource views | S1 |
| FastAPI backend Deployment | Trusted context, agent, MCP client, SDK collectors and evidence; RAG/history added S3 | S1 |
| Upstream Kubernetes MCP Deployment | Read-only cluster exploration with its own scoped provider identity | S1 |
| Prometheus, Loki, Tempo, Grafana and Alloy | Metrics, sanitized logs, traces and private operational dashboards | S1 |
| Remote AWS MCP + direct AWS SDK | Agent exploration and independent inventory/metrics | S2 |
| Postgres / Qdrant / observation and ingest jobs | Scoped durable evidence/history and curated retrieval | S3 |
| Bedrock | Reasoning and separately configured embeddings | S3 |
| External backup destination | Native state recovery outside the cluster | S5 |
| Keycloak | Login and verified user identity; membership/grants remain backend policy | S6 |

One Vyom application chart and pinned vendor observability releases share a reproducible environment workflow. Optional Jev classification in S4 and conditional Vault in S6 are described in the [architecture](docs/ARCHITECTURE.md); they are not mandatory service dependencies. See the [interactive application overview](docs/diagrams/application.html), [interactive observability view](docs/diagrams/observability.html) and [observability design](docs/OBSERVABILITY.md) for further detail and verification limits.

## Start here

1. [Constitution](vyom-12-week-sprint-plan.md) — scope and six-sprint delivery order.
2. [Agent agreement](AGENTS.md) — how coding sessions work.
3. [Implementation plan](docs/IMPLEMENTATION_PLAN.md) — task details and acceptance.
4. [Tracker](docs/TRACKER.md) — authoritative task status and evidence.
5. [Current handoff](docs/HANDOFF.md) — where the next session starts.
6. [Architecture](docs/ARCHITECTURE.md) — intended S6 design and detailed diagrams.
7. [Verification](docs/VERIFICATION.md) — what constitutes proof.
8. [MCP integrations](docs/MCP_INTEGRATIONS.md) — upstream ownership, dual execution paths and deployment/auth gates.
9. [Observability](docs/OBSERVABILITY.md) — S1 metrics/logs/traces topology, privacy and live gates.
10. [Branding](docs/BRANDING.md) — canonical logo and reuse for the application, documents and future site.
11. [Decisions](docs/DECISIONS.md) — open choices and accepted implementation decisions.

First milestone: on Kind, ask which pods are unhealthy in a demo namespace and receive an answer citing the upstream Kubernetes MCP server through Vyom’s MCP client; the resource view uses a direct SDK path. The same real chat must expose Prometheus metrics, sanitized Loki logs and an OTel/Tempo trace through privately accessed Grafana. S1 adds 10 estimated hours; the aggregate is 12.5 weeks at current capacity, with twelve weeks still the target.

## Run the scaffold

Needs Node 26 with npm and [uv](https://docs.astral.sh/uv/); uv installs the pinned Python 3.13. Both servers bind to localhost only.

```sh
# terminal 1: API on http://127.0.0.1:8000
cd backend
uv sync --locked
uv run uvicorn vyom.api.app:app --host 127.0.0.1 --port 8000

# terminal 2: UI on http://127.0.0.1:5173, proxying /api to the backend
cd frontend
npm ci
npm run dev
```

Open the UI: the Backend card shows `ok` with the service name and version. `curl http://127.0.0.1:8000/api/health` returns the same data. Stop the backend and the card turns to `Unreachable` within 10 seconds, then recovers when the backend returns.

Checks, also run by [CI](.github/workflows/ci.yml):

```sh
cd frontend && npm run typecheck && npm run lint && npm run build
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest -q
```

## Run the observability stack on Kind

Needs Docker, kind, kubectl, Helm, curl and openssl. Nothing is published on host ports.

```sh
kind create cluster --config deploy/kind/cluster.yaml   # cluster "vyom", context kind-vyom
./scripts/observability-up.sh      # pinned Prometheus/Grafana, Loki, Tempo and Alloy; safe to re-run
./scripts/observability-check.sh   # login required, targets up, logs bounded, synthetic trace in Tempo
./scripts/mcp-up.sh                # pinned upstream Kubernetes MCP server behind an authenticating proxy, plus demo pods
./scripts/mcp-check.sh             # live: handshake, pod list equal to kubectl, callers and scope refused

kubectl --context kind-vyom -n observability port-forward svc/grafana 3000:80 --address 127.0.0.1
# http://127.0.0.1:3000  user admin, password in .local/grafana-admin-password
```

Reasoning endpoint (S1.4): OpenRouter with `anthropic/claude-haiku-5.5`. Run the live check yourself in a terminal that has the API key; it sends a few small requests, which costs a little. The key can be an environment variable in that terminal or an ignored file.

```sh
export OPENROUTER_API_KEY=...             # in your own terminal; or instead:
(umask 077; cat > .local/model-api-key)   # paste the key, press Enter, then Ctrl-D

./scripts/model-check.sh                  # live: tool-call round trip, refused arguments, wrong and missing key, no key in telemetry or bundle
```

The first install pulls about ten images and takes several minutes. `kind delete cluster --name vyom` removes everything, including stored telemetry. What is installed and its limits: [observability](docs/OBSERVABILITY.md#installed-on-kind-in-s19).

Backend layout under `backend/src/vyom/`: `api` (HTTP), `mcp_client` (outbound MCP through the official SDK with the endpoint registry, tool allowlist, limits and the reviewed Kubernetes pod-list tool; Vyom serves no MCP protocol), `evidence.py` and `context.py` (shared evidence contract and server-side scope), `telemetry.py` (payload-free JSON logs, `/metrics`, OTLP traces), `agent` (the reasoning adapter: LangChain `ChatOpenAI` against one OpenAI-compatible endpoint; the LangGraph workflow arrives in S1.5), `credentials.py` (credential references) and `collectors` (empty until S1.6).
