# Implementation plan

The [constitution](../vyom-12-week-sprint-plan.md) governs scope. [TRACKER](TRACKER.md) alone owns status. This plan replaces the old six-sprint schedule; historical results remain in session records. There is no current calendar estimate.

## Active rescope sequence

Work one dependency-ready increment at a time. For broad tasks, finish their listed sub-increments sequentially and retain the parent as partial until its live gate passes. File-level actions are in [the overhaul change map](OVERHAUL_CHANGE_MAP.md). [Continuous operations](CONTINUOUS_OPERATIONS.md) defines issue/job semantics. R10 blocks exposure; scope and recovery controls begin in R2, not at R10.

### R1 — Repository and local packaging cleanup

**Depends on:** —

Consolidate active documents and validate this roadmap, not obsolete sprint budgets. Preserve existing runtime work and historical session evidence. Make app/metrics/full profiles explicit; remove unsupported UI roadmap promises.

**Acceptance:** Documentation checker positive/negative tests; frontend checks; chart/profile rendering and shell validation; fresh Kind none/metrics application gates and optional full-profile regression. Record unavailable gates explicitly.

### R2 — Scoped Postgres resource and evidence foundation

**Depends on:** R1

Implement migrations, scoped Resource/Relationship/CollectionRun/Evidence contracts, native UID-backed identity, source provenance and safe projections. Preserve old transient citations through explicit compatibility mapping. Introduce Postgres and credential mounts only with the consuming persistence code.

**Acceptance:** Real Postgres transaction/migration/restore checks, cross-workspace denial and FK tests, UID recreation, failed/partial scan behavior and resolving persisted citations after restart.

### R3 — Scheduled Kubernetes inventory and workload detail

**Depends on:** R2

Collect Deployment/ReplicaSet/Pod ownership first, then cluster/nodes/namespaces, StatefulSet/DaemonSet, Service/EndpointSlice/Ingress/NetworkPolicy and PV/PVC. Add Job/CronJob/StorageClass and configuration metadata only with reviewed projections. Configurable schedules run independently of browser requests; stored list/detail/filter/pagination APIs drive UI.

**Acceptance:** Kind inventory equals authorized API data, workload detail resolves relationships, browser closed collection continues, duplicate workers cannot overlap unsafe reconciliation, complete scans detect absence and failed scans cannot; freshness and denial visible. MCP/model failure leaves inventory working.

### R4 — Manual workload investigation and diagnostic labs

**Depends on:** R3

Implement investigate_workload with inventory context and selective live MCP verification. Extend tools/RBAC only for reviewed safe evidence. Split into skill core, Pending branches, container/readiness branches and lab validation; each is a reviewable change.

**Acceptance:** Ten live Kind cases: crashloop, OOM, readiness, image pull, insufficient capacity, taint mismatch, node selector, service selector, pending PVC, rollout failure. Inspect evidence/citations and limitations; model outage, injection, tool limits and denied scope tests. Fixtures alone cannot close the gate.

### R4a — Continuous workload issue and automatic triage loop

**Depends on:** R4

Implement in order: deterministic changes/conditions and issue episodes; persisted leased jobs with budgets/idempotency; automatic workload skill; scoped conversation/UI; observed recovery. Use the lifecycle in CONTINUOUS_OPERATIONS. No new broker or multi-agent runtime.

**Acceptance:** One live Deployment change-to-failure-to-issue-to-diagnosis-to-follow-up-to-recovery loop. Repeat polls/retries yield one issue/result. Test restart, flapping, recovery races, partial/stale evidence, UID recreation and scope revocation. Model failure never blocks deterministic issue state.

### R5 — Kubernetes deterministic posture

**Depends on:** R4a

Add versioned deterministic rules and scoped findings/UI; approximately ten high-signal checks with policy parameters and distinct security/reliability/configuration categories. Model explanations consume findings, not invent them.

**Acceptance:** Positive/negative/unknown fixtures, reproducible Kind findings with evidence, safe missing-field handling, resolution and stale-data behavior; framework mapping accuracy checked when introduced.

### R6 — AWS native inventory

**Depends on:** R5

Collect EC2/ENI/VPC/subnets/routes/SG/NACL/gateways, ELB/target groups, EKS/nodegroups and basic IAM using native APIs. Resource Explorer can assist discovery, never replace detailed configuration sources. Expand one resource family at a time.

**Acceptance:** Stubber normalization/pagination/denial fixtures, scoped account/region relationships and authorized live inventory comparisons. LocalStack only where compatibility is proven. No chargeable provisioning inferred.

### R7 — AWS connectivity investigation

**Depends on:** R6

Implement investigate_connectivity with configuration path evidence, existing Reachability Analyzer results and available Flow Logs. Add reproducible Terraform fixtures without applying them absent explicit authorization. Follow with basic EC2 health and ALB target investigation.

**Acceptance:** SG, NACL and route/path failures, unhealthy ALB target and basic EC2 health diagnosed with evidence. Separate configuration from observed traffic; bounds and unknown paths tested. Sandbox apply/teardown needs task-specific authorization.

### R8 — AWS deterministic posture

**Depends on:** R7

Approximately ten tested networking/EKS/basic IAM checks; clear policy and category, evidence and remediation. Do not infer effective IAM access from one wildcard statement.

**Acceptance:** Rule correctness and false-positive fixtures, scoped evidence and safe unresolved states, authorized live examples. Framework mappings are metadata, not certification.

### R9 — Cross-platform relationships

**Depends on:** R8

Connect Kubernetes Nodes to EC2 using verified provider identity. Add Ingress/load-balancer/target-group/service links only where reliable source evidence exists.

**Acceptance:** No name-only inferred identity, account/cluster scope isolation, UID recreation and stale-edge handling; inspect real authorized EKS evidence before claiming delivery.

### R10 — Recovery and identity/exposure gate

**Depends on:** R4a

Implement verified identity/membership and current grants for every enabled live/historical surface, conversation and job. Reuse early scoped persistence and restore foundations. Gate applies before multi-user/remote exposure regardless of AWS task status.

**Acceptance:** Postgres restore preserves citations/issues; wrong/expired identity and two-workspace denial; grant revocation stops new and leased work; isolated provider credentials/sessions; production refuses fixed identity. Internal/localhost access until all enabled surfaces pass.
