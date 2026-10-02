# Vyom — Security Notes (stub)

This document will be expanded in FX.4. Quick rules:

- No K8s `Secret` objects for app secrets — Vault Agent sidecars only.
- Keycloak `sub` identifies a user; verified server-side membership resolves tenant and role. Never trust a tenant ID from a request body, header, query string, or tool argument.
- Roles checked in **both** UI and MCP wrappers (D2).
- Encrypted at rest in Postgres via `ENCRYPTION_KEY` (FX.2 upgrades to envelope encryption).
- Cloud credentials stored in Vault under `secret/tenants/{tenant_id}/providers/`.
- Bedrock reasoning/embeddings are restricted to `ap-south-1`, in-region models compatible with zero retention, no cross-region profiles, and no invocation-content logging. Application logs contain redacted metadata only; tenant content is never used for Vyom model training.
- D34 permits optional Jev intent classification through Vercel AI Gateway. It is disabled by default, restricts the gateway provider/model, requires gateway zero retention, and reads its API key from a Vault-rendered backend file. Gateway/provider data handling and geography are a separate B8.6 gate; an AWS-region guarantee does not extend to this external path. See [INFERENCE.md](INFERENCE.md) for minimization limits, escalation, and approval-file semantics.

- Kubernetes access requires tenant-owned cluster connections, permitted namespaces and separate cluster-wide grants. Dedicated read-only RBAC excludes Secret reads, exec/attach, proxy and mutation; normalize allowlisted fields and omit literal environment values. Collection/onboarding enforcement remains pending B11. See [KUBERNETES.md](KUBERNETES.md).
