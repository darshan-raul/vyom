# Vyom

Vyom is the product name. It replaces Cloud Compass (originally Cloud Cost Compass).

## Executive tagline

**Vyom: Grounded intelligence for the modern cloud.**

## Platform subheading

Tenant-isolated cloud operations. One explainable cockpit for spend, posture, and risk across AWS and Kubernetes.

## Technical pitch

Vyom turns scattered cloud telemetry into deterministic, RAG-grounded insight—orchestrated by LangGraph agents and secure MCP tooling.

## Naming and scope

Use **Vyom** in product copy, navigation, page titles, API documentation titles,
and active documentation. The future onboarding CLI is `vyom`. Existing
Kubernetes namespace/image references, Keycloak realm/client IDs, contract package
paths, repository directory, and Git remotes retain their historical names until
a coordinated identity migration is verified. This avoids breaking deployment,
authentication, or import compatibility during a copy change.

The first release includes AWS plus Kubernetes inventory, health/events, and
configuration posture. EKS, AKS, GKE, and self-managed clusters use the Kubernetes
API connector. Cloud billing/provider parity for GCP and Azure remains sequential
after AWS. The positioning describes the product direction; the tracker remains
the authority for what is implemented and verified.

Inference uses Bedrock reasoning/embeddings and optional actual TypeSafe Jev
through Vercel AI Gateway for intent classification. The old MiniMax client is
removed. Read-only tools and deterministic calculations/policy checks provide
the evidence; RAG and language models explain that evidence. Model outputs are
not inherently deterministic or correct.
