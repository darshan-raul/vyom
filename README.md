# Vyom

**Vyom: Grounded intelligence for the modern cloud.**

Tenant-isolated cloud operations. One explainable cockpit for spend, posture, and risk across AWS and Kubernetes.

Vyom turns scattered cloud telemetry into deterministic, RAG-grounded insight—orchestrated by LangGraph agents and secure MCP tooling.

Formerly Cloud Compass (originally Cloud Cost Compass). This repository is under
refactor; the positioning above describes the intended product. It is not yet an
operational or production-ready cloud/Kubernetes cockpit.

## What is implemented

| Area | Repository evidence | Remaining work |
|---|---|---|
| Vyom product identity | App title, login, sidebar, chat copy, favicon and shared `app/src/lib/brand.ts` | Browser/build validation; coordinated migration of historical deployment identifiers |
| Bedrock inference | RAG embedding facade, Titan V2 codec, Converse adapter, model/region allowlists and approval checks | Live access/policy evaluation, model selection, authenticated LangGraph wiring and corpus cutover |
| Actual Jev via Vercel | Native evaluation HTTP adapter for `typesafe-ai/jev`; typed intent hints, minimized input and escalation | Vault/gateway activation, external data-handling evidence and routing evaluation; disabled by default |
| Kubernetes internals | `mcp-server/connectors/kubernetes/`: grant checks, bounded API lists, allowlisted normalization, topology, health/posture and in-memory reconciliation | Backend membership/grant resolver, onboarding, persistence/watch worker, private collector, public tools/UI and live flavor evidence |
| Legacy MCP | `get_costs` and `get_resources` AWS functions in `mcp-server/server.py` | JWT verification, server-resolved tenant/role, normalized providers, pagination and browser HTTP adapter |
| RAG service | `/health`, `/retrieve`, `/ingest`, `/history`; tenant/model-versioned vectors | Replace trusted tenant headers, secure history/corpus access, restrict arbitrary ingest and implement lifecycle/transactions |
| Browser app | Refine/Vite/shadcn-style shell, pages, Keycloak scaffold and chat UI | Resolve existing imports/auth/API mismatches, lock/install dependencies and verify build; no Kubernetes page yet |
| LangGraph agent | Reasoning/classification adapters exist | No graph, authenticated chat/SSE endpoint or citation/evaluation runtime yet |
| Deployment | Raw manifests, Helm chart and Kind/EKS scripts exist | Reconcile deployment sources, identity, persistence and service routing; no end-to-end release has been verified |

The **28 inference tests** and **25 Kubernetes tests** run offline. They verify
adapter behavior with fake boundaries, not live Bedrock/Jev access, deployed
identity isolation, or EKS/AKS/GKE connectivity. Python contract tests exist but
cannot run here without their dependencies. The frontend build also remains
unverified because Node dependencies are absent.

## First-release scope

AWS comes first for cloud-provider billing/inventory/security; GCP then Azure
follow their release gates. Kubernetes has a separate API connector that can
represent **EKS, AKS, GKE and self-managed clusters** without claiming cloud
billing parity for those providers.

- Daily AWS cost, cloud inventory/change detection, Security Hub/direct checks,
  weekly digest and cited read-only chat.
- Kubernetes cluster/workload inventory, topology, health/recent events and
  bounded configuration posture. Access is tenant → cluster → permitted
  namespaces, with separate grants for cluster-wide objects.
- Later: historical monitoring integration, Kubernetes cost allocation and
  rightsizing, formal governance/compliance, image/SBOM analysis and deeper
  operational diagnostics. Namespace costs must reconcile to infrastructure
  charges without counting node costs twice. Write remediation remains deferred.

The Kubernetes code is an internal collection-to-analysis flow; it is deliberately
not registered in the legacy unauthenticated MCP server. Watch collection,
persistence, private-cluster outbound collection and live support evidence remain
B11 work. The original 12-week AWS-only estimate needs rebaselining for this scope.

See the [execution tracker](docs/BETA_EXECUTION_PLAN.md),
[Kubernetes implementation and delivery boundaries](docs/KUBERNETES.md),
[inference configuration](docs/INFERENCE.md) and [roadmap](docs/ROADMAP.md).

## Target architecture

The browser authenticates through Keycloak. Backend membership resolution must
produce tenant/role context before LangGraph or MCP can call a connector.
LangGraph will use Bedrock for reasoning/embeddings and optional Jev for intent
classification. Authorized cloud and Kubernetes collectors produce normalized
objects, relationships, findings and evidence for Postgres and tenant-scoped RAG.
Calculations and explicit policy checks remain deterministic code.

Kind is the local/CI target; the hosted platform targets a dedicated EKS account
in `ap-south-1`, with self-managed Postgres, Qdrant, Vault and Keycloak. Bedrock
has a regional data-policy gate; external Jev classification has a separate gate.
Neither boundary is established by the offline adapters alone.

The [architecture document](docs/ARCHITECTURE.md) describes this target. The
[September infrastructure diagram](docs/diagrams/aws-beta-infrastructure.html)
is historical and predates Vyom/Kubernetes collection.

## Actual repository layout

```text
cloud-compass/                       # current directory; product is Vyom
├── AGENTS.md                        # decisions and invocation log
├── app/                             # browser shell, auth, pages, shared brand
├── contracts/python/                # v1 Pydantic contracts and tests
├── docs/                            # scope, roadmap, trackers and release gates
├── mcp-server/
│   ├── server.py                    # legacy AWS MCP tools
│   ├── connectors/kubernetes/       # internal collection/analysis module
│   └── tests/test_kubernetes.py
├── rag-service/
│   ├── routers/                     # retrieve, ingest, history
│   ├── embed/                       # Bedrock facade and text chunking
│   ├── inference/                   # Bedrock + actual Jev adapters
│   ├── qdrant/                      # tenant/model-versioned vector access
│   └── tests/                       # offline inference/vector tests
├── migrations/                      # 001_initial_schema.sql, 002_seed_tenants.sql
├── infra/                           # raw manifests, Helm chart and Kind config
└── scripts/                         # setup-kind, deploy-eks, test-inference
```

There is no agent service, alerts service, cloud-provider abstraction directory,
CLI/OpenTofu onboarding implementation, or formal compliance pack yet. Planned
MCP names such as `kubernetes.*` and `cost.get_costs` are acceptance targets;
the running legacy server currently registers `get_costs` and `get_resources`.

## Local verification

From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3.11 scripts/test-inference.py --sandbox-selector-poll
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=mcp-server python3.11 -m unittest discover -s mcp-server/tests -v
helm template vyom infra/k8s/charts/cloud-cost-compass --namespace cloud-cost-compass
```

The selector flag is a test-process workaround for this managed sandbox; normal
hosts can run the inference runner without it. Helm rendering is a manifest
syntax check, not deployment evidence; it currently emits a Postgres TLS-values
warning. Full service checks require dependencies and B2 quality-gate repairs.

For frontend development:

```bash
cd app
npm install
npm run lint
npm run build
npm run dev
```

The app defines these scripts; no lockfile is present yet. Vite listens on 5173
and defaults to in-cluster backend proxy hostnames. For local backends set
`VITE_MCP_PROXY`, `VITE_RAG_PROXY` and `VITE_ALERTS_PROXY` explicitly; the alerts
service and chat endpoint do not exist yet. `VITE_KEYCLOAK_*` must match the
reconciled realm/client configuration. These commands are not a verified
end-to-end setup instruction until B1/B2 pass.

## Deployment and identity compatibility

The namespace, Kind cluster, image prefix and Helm chart still use
`cloud-cost-compass`; Keycloak configurations retain historical identifiers
that are not yet consistent across app/manifests. Package imports use
`cloud_compass_contracts`. The repository directory/remotes remain owner-managed.
See [branding compatibility](docs/BRAND.md). Product copy changes do not migrate
these identities or repair the authentication boundary.

Existing setup/deployment scripts are in `scripts/`. Follow the
[release checklist](docs/RELEASE_CHECKLIST.md) before using them for promotion;
Kind/EKS health, persistence, rollback and isolation gates are still pending.
No public service should be treated as tenant-safe based on the current legacy
MCP/RAG interfaces: MCP accepts a caller-supplied tenant argument, RAG trusts a
tenant header, and the browser currently conflates Keycloak `sub` with tenant
identity. B1.3–B1.7 must resolve these gaps before onboarding tenants or exposing
Kubernetes tools.

Bedrock configuration, Vault-rendered approval/key paths and the explicit vector
reindex requirement are documented in [INFERENCE.md](docs/INFERENCE.md).
Kubernetes transport expects backend-enrolled HTTPS endpoints and tenant/cluster
Vault-rendered credentials; it never executes kubeconfig hooks. Enrollment and
network-destination validation remain B11.2 work.
