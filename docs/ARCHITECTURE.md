# Vyom — intended end-of-S6 architecture

**Design target, not deployed state.** The 12-week outcome remains a personal alpha with a tested initial tenant boundary. The reset remains in force. This revision adopts the owner's MCP host/client decisions and full observability from S1 while preserving sprint order, frontend stack, inference progression, RAG, recovery and later Keycloak. S1 now estimates 50 hours including reserve; the total is 250 hours/12.5 weeks at current capacity, with twelve weeks still the target.

The [interactive overview](diagrams/application.html) and [editable JSON](diagrams/application.json) show the two execution paths and the S1 observability branch. The [dedicated observability view](diagrams/observability.html) expands the collection/query topology described in [OBSERVABILITY.md](OBSERVABILITY.md). See [verification status](diagrams/README.md) for rendering limits and [MCP integration design](MCP_INTEGRATIONS.md) for the detailed deployment/authentication matrix and primary sources. Diagrams below are editable Mermaid source.

## 1. Components and responsibilities

```mermaid
flowchart TB
    ui[Vyom UI / future CLI<br/>Ordinary backend API client]
    subgraph backend[Vyom backend / FastAPI]
        auth[Server context and authorization<br/>Fixed operator initially, Keycloak memberships S6]
        lg[Agent / LangGraph<br/>Bounded reasoning and tool selection]
        host[MCP client / host<br/>Connection registry, policy, credentials, evidence]
        deterministic[Deterministic product logic<br/>Inventory, sync, dashboards, calculations]
        persistence[Persistence / RAG modules<br/>Normal libraries and APIs]
        auth --> lg --> host
        auth --> deterministic
        lg --> persistence
        deterministic --> persistence
    end
    subgraph target[Target Kubernetes cluster]
        kmcp[Upstream Kubernetes MCP Deployment<br/>Preferred containers/kubernetes-mcp-server]
        kapi[Kubernetes API<br/>Scoped RBAC]
        kmcp -->|In-cluster ServiceAccount| kapi
    end
    awsMCP[AWS-managed MCP Server<br/>Or verified appropriate AWS-provided capability]
    aws[AWS APIs<br/>Read-only IAM]
    pg[(Postgres · S3)]
    q[(Qdrant · S3)]
    model[Reasoning endpoint<br/>Compatible API S1, Bedrock S3]
    future[Later registered MCP servers<br/>GitHub, IaC, docs, FinOps]
    ui -->|HTTP API| auth
    lg -->|Model SDK/API| model
    host -->|Authenticated MCP| kmcp
    host -->|Authenticated remote MCP| awsMCP
    awsMCP -->|Scoped AWS identity| aws
    deterministic -->|Direct Kubernetes SDK| kapi
    deterministic -->|Direct AWS SDK| aws
    persistence -->|SQL client| pg
    persistence -->|Qdrant client| q
    host -.->|Later, separately gated| future
    obs[Observability namespace · S1<br/>Alloy, Prometheus, Loki, Tempo, Grafana]
    backend -.->|Owned OTel spans + sanitized container logs| obs
    obs -.->|Prometheus scrape /metrics| backend
```

Vyom owns orchestration and integration policy. It does not build a production Kubernetes MCP protocol implementation or a general-purpose AWS MCP server. The upstream Kubernetes server is a separate pinned workload, not a Vyom Python entrypoint. An AWS signing proxy, if needed, is transport support for the host rather than a cloud-tool wrapper.

Deterministic product services handle bulk/paginated collection, schedules, arithmetic, dashboards and persistence through normal SDKs/APIs. MCP is the preferred boundary for agent-driven exploration. Both paths produce a shared evidence contract, with distinct provenance. A table must not become unavailable merely because an independent MCP integration failed.

The UI/CLI never selects upstream credentials or contacts MCP directly. The CLI is shown as a future client, not added to S1. Postgres, Qdrant, embeddings, internal APIs and application logic are not routed through MCP. Optional additional servers remain future integrations, not new six-sprint tasks.

## 2. Deployment topology: local KIND and EKS

### Local KIND — S1

```mermaid
flowchart LR
    dev[Developer browser<br/>localhost only]
    model[Configured compatible model endpoint]
    subgraph kind[KIND cluster · same cluster monitored first]
        ui[UI Deployment / internal Service]
        subgraph app[Vyom API Deployment]
            lg[LangGraph + MCP client]
            sdk[Direct pod SDK projection]
        end
        svc[Private authenticated MCP endpoint<br/>ClusterIP Service for HTTP]
        upstream[Upstream Kubernetes MCP Deployment<br/>Pinned image + read-only config]
        msa[Dedicated MCP ServiceAccount<br/>Demo namespace Role/RoleBinding]
        csa[Separate collector ServiceAccount<br/>Scoped read permissions]
        kapi[Kubernetes API]
        demo[Demo namespace / test pods]
        ui -->|Normal HTTP API| app
        lg -->|MCP over chosen secure transport| svc
        svc --> upstream
        upstream -->|In-cluster credentials| msa
        msa --> kapi
        sdk --> csa --> kapi
        kapi --> demo
        subgraph observability[observability namespace · S1]
            alloy[Alloy DaemonSet<br/>Node-local logs + OTLP traces]
            prom[Prometheus + cluster exporters]
            stores[Loki + Tempo<br/>PVCs / initial 48h retention]
            grafana[Grafana<br/>Provisioned data sources + two dashboards]
            alloy -->|Logs + traces| stores
            grafana -->|Query logs / traces| stores
            grafana -->|Query metrics| prom
        end
        app -.->|OTLP traces| alloy
        logs[Allowlisted node-local container logs] -->|Read once per node| alloy
        prom -.->|Scrape /metrics| app
        prom -.->|Scrape health| alloy
    end
    dev -->|Localhost port-forward| ui
    lg -->|Backend-only model key| model
    dev -->|Authenticated localhost port-forward| grafana
```

The MCP endpoint is private and authenticated without requiring early Keycloak. Prefer supported Streamable HTTP; the Service is conditional on network transport. If an existing authentication/TLS proxy is selected, the raw server port must not bypass it. The MCP server uses its ServiceAccount for Kubernetes API access; do not forward a frontend token as Kubernetes authority. No developer-admin kubeconfig is mounted.

S1 acceptance covers Deployment, Service when needed, ServiceAccount, minimal RBAC, read-only tool selection, safe config/credential mounts, probes/resources, sanitized logs and connection health. NetworkPolicy is optional end-of-roadmap hardening; if added, verify CNI enforcement rather than claiming security from YAML alone. Secret access, writes, exec and raw logs remain disabled. The deterministic collector has its own scoped identity. Endpoint/image/config compatibility and actual safe tool outputs must be proven before the live gate.

### EKS — S2 onward, with S3/S6 additions labelled

```mermaid
flowchart TB
    user[Operator, authenticated tenants only after S6]
    subgraph region[Platform AWS region · ap-south-1]
        subgraph eks[EKS cluster]
            entry[Private UI/API Services<br/>HTTPS ingress only after S6 gates]
            api[Vyom API / agent / MCP client]
            collect[Direct SDK collectors<br/>Scheduled jobs from S3]
            kmcp[Upstream Kubernetes MCP<br/>Private Service + Deployment]
            ksa[MCP ServiceAccount / minimal RBAC]
            csa[Collector ServiceAccount / minimal RBAC]
            kapi[Kubernetes API / metrics API]
            irsa[Temporary IAM workload identities<br/>Separate agent and collector scopes]
            telemetry[Observability namespace · S2 carryover<br/>Prometheus, Loki, Tempo, Alloy, Grafana]
            state[Postgres + Qdrant · S3<br/>Keycloak durable state · S6]
            entry --> api
            api -->|MCP| kmcp --> ksa --> kapi
            collect -->|Direct SDK| csa --> kapi
            api -->|Normal persistence APIs| state
            collect -->|Normal SQL client| state
            api -->|Resolve scoped role| irsa
            collect -->|Resolve scoped role| irsa
        end
        bedrock[Bedrock · S3<br/>Reasoning and embeddings]
    end
    awsMCP[AWS-managed MCP endpoint<br/>Region verified separately, remote dependency]
    aws[AWS service APIs<br/>Configured account / resource region]
    backup[Protected backup destination outside cluster · S5]
    user -->|Localhost port-forward before S6| entry
    api -->|Signed/authenticated remote MCP| awsMCP
    awsMCP -->|IAM-authorized reads| aws
    collect -->|Direct AWS SDK| aws
    api -->|Model SDK/API| bedrock
    state -->|Native consistent backups| backup
    backup -->|Clean restore drill| state
    api -.->|Owned traces + sanitized logs| telemetry
    collect -.->|SDK/job traces + sanitized logs| telemetry
    telemetry -.->|Prometheus scrape| api
    user -->|Operator-only authenticated port-forward| telemetry
```

AWS-managed MCP is outside the EKS deployment, not a pod or custom wrapper. Endpoint region is distinct from the platform and monitored-resource region; source checks currently list a `us-east-1` managed endpoint. S2 verifies availability, routing/data handling, credentials and capability coverage before activation. See [AWS endpoint reference](https://docs.aws.amazon.com/general/latest/gr/aws-mcp.html).

Kind and EKS share chart structure and pinned upstream version with environment-specific values. Kubernetes RBAC and AWS IAM are different authorization systems. IRSA for AWS credentials does not grant Kubernetes reads. Bedrock reasoning/embedding permissions start S3; AWS MCP uses its own verified connection authentication and least-privilege scope. The full observability stack starts on Kind in S1, carries the same pins to EKS in S2 with validated storage/resources, and is hardened in S5. Pinned vendor releases share the reproducible environment workflow with the one Vyom chart. Inaccessible managed control-plane targets are labelled explicitly; Metrics Server/CloudWatch product sources remain separate.

The full Kubernetes deployment checklist and credential matrix live in [MCP_INTEGRATIONS.md](MCP_INTEGRATIONS.md). S6 initially isolates upstream Deployments/ServiceAccounts by tenant grant scope. No remote-cluster enrollment, broad service mesh, generic gateway or multi-region platform is introduced.

## 3. Question-to-evidence sequence

```mermaid
sequenceDiagram
    actor U as User
    participant API as Vyom backend
    participant G as LangGraph
    participant L as Model adapter
    participant H as MCP host/client
    participant K as Upstream Kubernetes MCP
    participant A as AWS-managed MCP
    participant P as Provider API
    participant R as Normal persistence/RAG APIs
    U->>API: Question + resource filters, JWT only S6
    API->>API: Resolve fixed context or verified membership/grants
    API->>G: Authorized context and budgets
    G->>L: Supported question + allowed tool schemas
    L-->>G: Untrusted proposed tool and arguments
    G->>H: Request registered capability
    H->>H: Validate scope, operation, endpoint binding and budgets
    alt Kubernetes investigation
        H->>K: Authenticated MCP call to authorized endpoint
        K->>P: Kubernetes API read with scoped ServiceAccount
        P-->>K: Resources or denied/partial/error
        K-->>H: Upstream result
    else AWS investigation
        H->>A: Remote MCP with scoped temporary identity
        A->>P: AWS API read under IAM
        P-->>A: Resources or denied/partial/error
        A-->>H: Upstream result
    end
    H->>H: Minimize and normalize evidence, reject unsafe output
    H-->>G: Source, time, coverage, evidence IDs and limitations
    opt Runbook guidance / history from S3
        G->>R: Scoped retrieval via normal libraries
        R-->>G: Authorized document/history evidence
    end
    G->>L: Observations and guidance as data, not instructions
    L-->>G: Facts / hypotheses / next checks with citations
    G->>G: Validate referenced evidence IDs and limits
    G->>R: Persist through normal SQL API from S3
    G-->>API: Answer and inspectable evidence
    API-->>U: Grounded response or explicit limitation
    Note over API,H: Owned OTel request/graph/model/MCP/normalization spans from S1
    Note over K,P: Upstream internal spans only if supported; external internals not promised
```

The host resolves authority before any upstream call. Neither managed AWS MCP nor the Kubernetes upstream is assumed to interpret Vyom tenant IDs. RBAC/IAM enforce provider scope; host policy constrains capabilities, arguments, evidence and user access. Missing authorization prevents calls altogether. Provider/MCP failure yields an explicit integration limitation; a direct-SDK fallback must be intentional, labelled and cannot pass an MCP acceptance gate.

S1 has one bounded tool round; S4 allows bounded sequences across registered capabilities. Model-provider integration remains a separate SDK/API path, preserving the original S1 compatible-model and S3 Bedrock milestones. MCP tool output is untrusted, even when the tool is supplied upstream.

## 4. Deterministic collection, knowledge and persistence

```mermaid
flowchart TB
    dash[Dashboard refresh] --> service[Deterministic backend service]
    timer[Observation schedule · S3] --> service
    service --> sdk[Direct AWS / Kubernetes SDKs]
    sdk --> api[Provider APIs]
    api --> normalize[Scope + minimize + normalize evidence]
    normalize --> db[(Postgres observations/errors/history)]
    db -->|Authorized query, freshness labels| dash
    agent[Agent MCP result] --> normalize
    corpus[Curated versioned runbooks] --> job[Operator ingest job]
    job --> embed[Bedrock embedding SDK]
    embed --> q[(Qdrant scoped/model-version collection)]
    query[Authorized query] --> retrieval[API retrieval module]
    retrieval -->|Embedding SDK| embed
    retrieval -->|Qdrant client| q
    q -->|Document/section/version citations| retrieval
    retrieval --> answer[Answer and evidence panel]
    db -->|Reauthorize historical evidence| answer
    signals[Owned OTel spans, sanitized logs and metrics<br/>Collectors / embeddings / retrieval / SQL / vector / jobs]
    service -.->|Timing / outcome / freshness| signals
    job -.->|Timing / outcome| signals
    retrieval -.->|Timing / outcome| signals
```

Database, vector, schedule and ordinary service communication never require an MCP round trip. Direct collectors and agent evidence meet at a normalized contract, not at a new universal protocol server. Record transport/provenance so observations from different collection times are not treated as contradictory automatically. Deterministic findings/calculations stay in code.

Retain original S3 requirements: idempotent chunk IDs and ingest, model/dimension-version collections and reindexing, fresh migration ledger, workspace scope, observation idempotency and explicit stale/error records. Postgres stores product evidence/history; Prometheus stores operational time-series from S1. Neither implies general product metrics-history or agent telemetry analytics. Curated retrieval remains inside the API; no upload/crawler or separate RAG service is added.

## 5. Authentication, authorization and connection isolation

```mermaid
flowchart TD
    principal[Fixed operator S1–S5<br/>Verified Keycloak subject S6] --> resolver[Server context / memberships / role]
    resolver --> grants[Tenant-owned connection + current resource grants]
    grants --> host[MCP host policy and endpoint selection]
    grants --> direct[Direct SDK collector policy]
    host --> kscope[Scoped Kubernetes MCP endpoint<br/>Deployment + ServiceAccount per tenant grant scope]
    host --> awscope[Account-bound AWS MCP credential/session]
    kscope --> rbac[Kubernetes RBAC: namespaces / explicit cluster-wide reads]
    awscope --> iam[AWS IAM: underlying read actions / resource scope]
    direct --> provider[Scoped SDK ServiceAccount / IAM identity]
    grants --> history[History / citations / retrieval / jobs authorization]
    revoke[Revoke grant or membership] --> resolver
    revoke --> invalidate[Invalidate sessions/caches, reconcile permissions<br/>Block reads while bindings are stale]
    invalidate --> host
    invalidate --> direct
    invalidate --> history
    grants --> telemetry[Telemetry access decision · S6<br/>Operator-only stays private; exposed queries/Grafana enforce grants]
    invalidate --> telemetry
```

There are distinct identities: the user accessing Vyom, Vyom authenticating to an MCP endpoint, and the endpoint accessing a provider API. Keycloak resolves the first only in S6. In-cluster ServiceAccount credentials resolve the Kubernetes provider identity from S1. An endpoint token must not accidentally change the provider identity. AWS calls use verified temporary workload/account scope; do not copy preview-era policies without checking current AWS guidance.

The initial tenant gate uses isolated Kubernetes MCP deployments/ServiceAccounts per distinct tenant grant scope rather than a shared overprivileged endpoint. No additional upstream protocol implementation is needed. Revocation must affect live calls, pooled sessions, deterministic jobs and stored evidence. Client/model tenant headers, namespace arguments, server URLs and credential profiles never grant authority. A read-only setting or tool annotation is insufficient without effective RBAC/IAM and output minimization.

Viewer/operator roles govern product actions; all cloud and Kubernetes operations in these six sprints remain read-only. Later writes require a separate explicit policy/use case. Future GitHub/IaC/documentation/FinOps MCP connections use the same registered-client boundary and receive their own permission and data-handling review.

## 6. Optional external classifier and secret storage

```mermaid
flowchart LR
    request[Authorized request text] --> gate{Jev enabled and<br/>data-handling gate passed?}
    gate -->|No| lg[Core Bedrock workflow]
    gate -->|Yes| redact[Minimize / redact<br/>Exclude credentials, identity,<br/>tool results and retrieved context]
    redact --> gateway[Vercel AI Gateway → actual Jev]
    gateway --> validate[Validate typed category + confidence]
    validate -->|Known and sufficient confidence| hint[Routing hint only]
    validate -->|Unknown / failure / uncertainty| lg
    hint --> lg
    lg --> auth[Normal code-based authorization<br/>and calculations remain mandatory]
```

Jev is evaluated in S4, disabled by default, and never necessary for the core journey. Geography, retention and minimization must pass before activation. The initial S1 compatible reasoning provider and this optional classifier are separate data-processing paths with separate configuration and checks.

Vault is conditional in S6 if additional connection secrets justify it; it is not a mandatory S1 deployment. Early model keys use a private runtime injection mechanism. AWS workload IAM roles avoid embedding AWS keys in application configuration. Secret segregation and rotation must be verified for whichever S6 mechanism is selected.

## 7. How the architecture grows

| Stage | New capability | New runtime/state complexity |
|---|---|---|
| S1 | One live pod question, table, citations and correlated signals | UI/API/agent/MCP + direct pod view; Prometheus, Loki, Tempo, Alloy, Grafana and OTel |
| S2 | EC2, workload health and current metrics | Same release/upstream K8s MCP on EKS; remote AWS-managed MCP plus direct SDK paths; same observability pins on EKS |
| S3 | Bedrock reasoning, curated guidance and memory | Postgres + Qdrant; operator ingest and observation job; embedding adapter; instrument Bedrock/RAG/state/jobs |
| S4 | Bounded investigation, daily cost and two findings | Additional upstream capabilities/graph paths; optional Jev classifier; investigation/cost timings |
| S5 | Recovery, fault handling and release confidence | Backup destination and automation; harden existing telemetry, storage/sampling, alerts and recovery |
| S6 | Tested membership and namespace isolation | Keycloak, connection/credential isolation, scoped upstream deployments and conditional Vault/HTTPS exposure; tested telemetry access policy |

No Azure/GCP provider APIs, remote-cluster enrollment, event streaming pipeline, Security Hub platform, compliance, SBOM, external alert channels or general-purpose agent telemetry analytics is implied by the final design. Those remain outside the constitution's core timebox.

## 8. Operational telemetry from S1

The collection/query arrows below do not make telemetry a synchronous application dependency. All components are planned, undelivered. The [observability design](OBSERVABILITY.md) owns detailed collection, privacy, retention and failure requirements.

```mermaid
flowchart TB
    backend[Vyom API / LangGraph / model and MCP clients<br/>Owned OTel spans + /metrics]
    logs[Node-local allowlisted container logs<br/>Sanitized JSON / trace_id / span_id]
    infra[Kubernetes exporters<br/>kube-state-metrics + node exporter]
    subgraph obs[observability namespace · S1 Kind / S2 EKS]
        alloy[Alloy DaemonSet<br/>Separate observer SA / bounded buffers]
        prometheus[Prometheus<br/>Single instance / PVC]
        loki[Loki<br/>Single binary / PVC]
        tempo[Tempo<br/>Monolithic / PVC]
        grafana[Grafana<br/>Cluster + Vyom dashboards / data source links]
        alloy -->|Logs| loki
        alloy -->|Traces| tempo
        prometheus -->|Scrape health| alloy
        grafana -->|Query metrics| prometheus
        grafana -->|Query logs| loki
        grafana -->|Query traces| tempo
    end
    backend -.->|Async bounded OTLP traces| alloy
    logs -->|Read once on each node| alloy
    prometheus -->|Scrape /metrics| backend
    prometheus -->|Scrape| infra
    operator[Operator] -->|Private authenticated localhost port-forward| grafana
```

Initial 48-hour retention and 100% demo tracing require finite PVC/resources/volume budgets and implementation-time pin checks. Logs are collected once through Alloy, without a second OTLP stdout path. Trace IDs belong in log fields/structured metadata, not indexed Loki or metric labels; metric dimensions are bounded. Drop sensitive headers/URLs, credentials, prompts, answers, tool bodies, pod environment values and unsafe exceptions at source. Upstream debug/payload logs must be disabled before collection.

S1.8 requires a real chat and induced provider/MCP failure with applicable metrics, sanitized logs and owned-component spans; demonstrate bidirectional Loki/Tempo navigation. Independently interrupt telemetry to prove bounded application behavior, observable loss/drops and recovery. S2 repeats these on EKS, S3–S4 instrument new paths, S5 tests alerts/storage/sampling/recovery, and S6 enforces the telemetry access decision. Observer log access does not authorize agent log tools. Internal Services and tenant labels alone are not endpoint authentication or tenant isolation.
