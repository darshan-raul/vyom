# Cloud Compass — Beta Release Checklist

This checklist governs promotion to the personal-alpha EKS environment and the later external beta. It is the release-control record required by B0.3; B2.5 and B3.4 must make the referenced build, smoke, immutable-image, and rollback paths fully automated before an EKS release can pass.

## Release rules

1. A clean Kind build, test, and smoke pass is required before every EKS deployment.
2. Only the project owner may approve an EKS deployment or a live personal-AWS verification. Record that approval in the release evidence.
3. EKS releases use immutable image digests. A failed EKS health or smoke gate causes an immediate rollback to the previously recorded digest; fix-forward is allowed only in Kind.
4. Live personal-AWS verification is read-only from Cloud Compass. The sole permitted controlled change is one made outside Cloud Compass to a dedicated resource tagged `cloud-compass:beta-test=true`, to prove the CloudTrail path.
5. Never place credentials, tokens, raw cloud-event payloads, resource names/ARNs, or chat content in release evidence.

## Evidence record

Create one dated file at `docs/releases/YYYY-MM-DD-<environment>-<revision>.md` from the template in [`docs/releases/README.md`](releases/README.md). It must list the revision, immutable image digests, approver, commands run, summarized results, deployment revision, rollback result where exercised, and final pass/fail decision.

## Gate A — Kind (required for every promotion)

Run from a clean checkout using the dependency and quality commands established by B2.1/B2.2, then run:

```bash
./scripts/setup-kind.sh
kubectl get pods -n cloud-cost-compass
kubectl wait --for=condition=ready pod --all -n cloud-cost-compass --timeout=5m
```

Record a pass only when the documented Kind smoke runner from B2.5 succeeds. Its required journey is:

1. Browser login succeeds.
2. A cross-tenant denial test succeeds.
3. Simulated connection and simulated cost, inventory, finding, and event data are visibly labelled and available.
4. Costs, Inventory, Security, and Chat show loading, empty, stale, denied, and partial-failure states as applicable to the current milestone.
5. App, MCP, RAG, Postgres, Qdrant, Vault, and Keycloak health/readiness checks succeed.

Any failed command, failed isolation check, unhealthy workload, or unlabelled simulated data blocks promotion.

## Gate B — EKS deployment and smoke

Prerequisites: Gate A passed for the same revision, owner approval recorded, selected deployment source is reconciled by B3.2, and image digests are recorded.

Deploy using the B3.4 promotion command. Then, at minimum, verify each changed stateless service:

```bash
kubectl rollout status deployment/app -n cloud-cost-compass --timeout=5m
kubectl rollout status deployment/mcp-server -n cloud-cost-compass --timeout=5m
kubectl rollout status deployment/rag-service -n cloud-cost-compass --timeout=5m
kubectl get pods -n cloud-cost-compass
```

Run the same browser and API smoke journey as Gate A against the HTTPS EKS endpoint. Confirm TLS, Keycloak redirect URI/login/logout, tenant-isolation denial, service health, source labels, and only the features available at the release milestone.

If any EKS health or smoke check fails, immediately roll back every changed stateless deployment to its previous revision, for example:

```bash
kubectl rollout undo deployment/app -n cloud-cost-compass
kubectl rollout status deployment/app -n cloud-cost-compass --timeout=5m
```

Record the failed gate, rollback commands, resulting revision, and post-rollback health. Do not attempt a fix-forward deployment to EKS within that release record.

## Gate C — simulated AWS proof

Against EKS, run the deterministic fixture suite introduced by B2.6. It must demonstrate normal data, an authorization failure, throttling/partial failure, a cost spike, security findings, and an event; all output must be labelled simulated. Record fixture IDs or test names and summary only.

## Gate D — live personal-AWS proof

Run only after Gates A–C pass and owner approval is recorded. Verify the personal AWS connection is active and Cloud Compass performs only its documented read-only AWS calls. Review cost freshness, inventory snapshot status, Security Hub/direct-check coverage, and cited chat output without copying tenant content into the evidence record.

For the controlled CloudTrail proof, the owner changes only the dedicated resource tagged `cloud-compass:beta-test=true` using normal AWS tooling. Confirm the resulting management event reaches the EKS worker and UI within the currently documented latency. Record timestamps/durations and a redacted outcome, not the raw event or resource identifier.

## Release decision

The owner signs the evidence record `pass`, `fail and rolled back`, or `not applicable to this milestone`. A live-AWS gate may be `not applicable` only before B9; it is mandatory for B9.5 and later. An unresolved failure blocks promotion and creates a tracked remediation item.
