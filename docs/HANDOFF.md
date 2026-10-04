# Current handoff

Updated: 2026-10-04. Latest session: [2026-10-04-10](sessions/2026-10-04-10.md).

## Current state

The separate [Kind chat POC](../poc/kind-chat/README.md) is implemented at `poc/kind-chat/`: branded React/TypeScript/Vite/shadcn chat and evidence UI, FastAPI direct Kubernetes collector and LangChain ChatPromptTemplate/ChatOpenAI using compatible Chat Completions, Dockerfiles, app Helm chart and target-reader Helm chart. Credentials are supplied via existing Secrets; target access is list-only in one namespace. No RAG/MCP or persistence. The main roadmap remains planning only; all S1–S6 tasks are pending and no sprint gate is closed.

Backend fixture tests (14) pass after the LangChain revision; frontend typecheck/build passed in the preceding session and its code is unchanged. The backend suite exercised real LangChain with mocked HTTP and bounded selector polling in a temporary sandbox harness; plain pytest stalled on thread wakeups. Owner explicitly reserved Docker/Kind/kubectl/Helm and live model checks: none were run, including image builds and chart lint/render. No application deployment or working live integration is claimed. No commit or push was performed.

## Next action

Owner: follow the POC README from `poc/kind-chat/` to create `app` and `target` Kind clusters, install target reader RBAC, supply target token/CA and model key Secrets, build/load images, set the reachable target API address and model configuration, install the app chart and open the localhost port-forward. A first question proves actual target/model connectivity; `/api/health` only proves startup configuration. Renew an expired target token; restart the API after model key rotation.

When main-roadmap implementation is requested, start **S1.1**, then prepare **S1.9**, following the constitution and implementation plan. Do not treat this direct-API POC as delivery of the required LangGraph/MCP/observability stack.

## Limits / environment

No browser/visual, container, chart or live checks were run. Kind cross-cluster routing, target TLS certificate coverage, image startup and provider compatibility await owner verification. Dependencies were installed from existing local caches because shell registry DNS was unavailable; the npm lockfile records normal registry URLs/integrity. Python tests ran in a temporary Python 3.12 environment backed by cached package archives, including langchain-core 1.4.7, langchain-openai 1.3.2 openai 2.41.1 and langsmith 0.8.15. Temporary code-check files under `/tmp/vyom-poc-*` are not product dependencies.

Earlier architecture/branding/RAG documentation remains in place. See [tracker](TRACKER.md) for sprint states and [POC decision](DECISIONS.md#separate-local-chat-poc--2026-10-04) for the owner-authorized exception.
