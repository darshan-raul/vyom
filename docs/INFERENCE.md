# Vyom inference refactor

As of 2026-10-03, RAG uses Bedrock embedding adapters; the MiniMax client and
deployment settings have been removed. A Bedrock Converse reasoning adapter and
an actual Jev classifier through Vercel AI Gateway are available as internal
Python modules. This is B1.8 adapter preparation. The authenticated LangGraph
agent, public chat/SSE API, live model selection, and production activation are
still B1/B3/B8 work.

## Model flow

After JWT verification and server-side membership resolution, the future
LangGraph `classify_intent` node can call
`inference.types.route_request(request_text, classifier)`. It receives a typed
cost/inventory/security/changes/Kubernetes planning hint, or an escalation result. Jev is
optional; disabled, excluded, malformed, unavailable, unknown, or uncertain
classification leaves planning to the Bedrock reasoning workflow. A hint never
authorizes a tool or limits the evidence the planner may need.

LangGraph remains responsible for planning, tenant-scoped RAG and read-only MCP
calls, synthesis, reflection, and citations. `BedrockChat.converse` preserves
content blocks and tool-use proposals. MCP wrappers must authorize every tool
call; authorization, calculations, and explicit controls remain deterministic
code. Neither inference adapter executes tools.

## Bedrock configuration

The runtime uses the fixed `ap-south-1` AWS endpoint and SDK workload credentials
(IRSA in EKS), with bounded timeouts/retries. It accepts allowlisted direct
foundation-model IDs and rejects inference profiles, ARNs, and endpoint URLs.
There is no automatic model/provider fallback. Current embedding encoding
supports Titan Text Embeddings V2 at 256, 512, or 1024 dimensions; this is an
implemented candidate, not a claim that regional access or model evaluation has
passed. Other embedding families require their own codec and tests.

Set operator-controlled environment variables:

```text
BEDROCK_REGION=ap-south-1
BEDROCK_EMBEDDING_MODEL_ID=<evaluated-direct-model-id>
BEDROCK_EMBEDDING_ALLOWED_MODELS=<approved-comma-separated-model-ids>
BEDROCK_EMBEDDING_DIMENSIONS=1024
BEDROCK_CHAT_MODEL_ID=<evaluated-direct-model-id>
BEDROCK_CHAT_ALLOWED_MODELS=<approved-comma-separated-model-ids>
BEDROCK_POLICY_FILE=/etc/secrets/bedrock-policy.json
```

No model or approval is enabled by the checked-in manifests. B3.5 must establish
regional availability, least-privilege IAM, actual AWS account zero retention,
and disabled invocation-content logging. Its deployment attestation must contain
`region: "ap-south-1"`, `data_retention_mode: "none"`,
`invocation_content_logging: false`, and an `approved_models` array. Adapters
read this JSON file before each call and fail closed if it is missing/denying.
The file is an operator attestation, not an AWS policy configuration or a live
policy audit. No approved attestation is included in the repository.

The implementation follows AWS's [Titan embedding request contract](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-titan-embed-text.html)
and [Converse API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html).
AWS documents the [account/region retention controls](https://docs.aws.amazon.com/bedrock/latest/userguide/data-retention.html);
the deployment gate must verify them rather than infer policy from the service name.

## Jev through Vercel

The classifier posts to `https://ai-gateway.vercel.sh/v1/evaluate` with model
`typesafe-ai/jev`, one Choice question, and a closed AWS/Kubernetes domain set. It uses
the native [Vercel evaluation HTTP API](https://vercel.com/docs/ai-gateway/modalities/evaluation),
so it does not require an upgrade of the browser's AI SDK or a direct TypeSafe
API key. Evaluation is distinct from the gateway's chat-completions API.

```text
JEV_ENABLED=false
AI_GATEWAY_API_KEY_FILE=/etc/secrets/ai-gateway-api-key
JEV_POLICY_FILE=/etc/secrets/jev-policy.json
```

The gateway key is read from a Vault-rendered file only; it never belongs in the
browser, a checked-in manifest, or a normal Kubernetes Secret. B8.6 must record
gateway and underlying provider data handling, locations, logging/retention, and
routing accuracy before rendering a policy with
`external_prompt_classification: true`, `data_handling_reviewed: true`,
`gateway: "vercel"`, `model: "typesafe-ai/jev"`, and `provider: "typesafe-ai"`.
Jev remains off until explicitly enabled; missing approval/key escalates locally.

Requests require gateway zero data retention and restrict inference to
`typesafe-ai`. No gateway fallback models are supplied. Responses from an
unexpected model/provider are rejected. If that provider cannot satisfy the
requested policy, classification fails and the application escalates; the code
does not relax the policy. Vercel's catalog slug may resolve to a changing model
version, so re-evaluation is required on provider changes. The catalogue does
not establish India-only processing. TypeSafe describes [enterprise ZDR](https://docs.typesafe.ai/legal);
availability for the gateway account still needs verification.

Only a short request string is accepted, never tenant context, chat history,
runbooks, or cloud tool outputs. Common account IDs, ARNs, UUIDs, emails, URLs,
and resource IDs are redacted. Obvious credential-bearing or oversized requests
bypass Jev. This is best-effort minimization; arbitrary secrets or identifiers
in free text cannot be reliably excluded by regexes. B8.6 must validate the
external boundary and the input policy before exposing this path to tenants.

Application routing requires selected probability >=0.8 and a >=0.2 gap over the
next category. When supplied, confidence must also be >=0.6. Missing confidence
stays absent, rather than being fabricated from probability. These are initial
configurable thresholds, not calibrated accuracy claims. Unknown, invalid, or
uncertain answers escalate. Calls have a five-second timeout and no application
retry, keeping an optional classifier outage from blocking the reasoning path.

## Vector transition

The active collection is `rag-{tenant_uuid}-v1-{embedding_spec_hash}`. The hash
includes model ID, codec, dimensions, normalization, and metric. Ingest and
retrieve use the same specification and check existing collection schema before
reading/writing. New collections use cosine distance and valid UUID point IDs.
Tenant UUID validation does not authenticate a caller; B1.6 still must replace
the existing trusted tenant headers with server-resolved membership context.

Legacy MiniMax `rag-{tenant_uuid}` collections stay untouched. Retrieval never
falls back to them or copies their vectors. When the selected version is absent,
retrieval reports unindexed/unavailable until seeding or reindexing. All Qdrant
calls target the selected tenant collection; other tenants' collections are not
enumerated. B8.5 must inventory the
source corpus per tenant, re-embed approved curated sources into the new namespace,
verify tenant-separated retrieval and metadata, and perform an explicit cutover
with rollback evidence. This refactor does not claim that a live migration ran.
No tenant document upload is authorized for beta; the pre-existing ingest route
still needs the access/corpus restrictions in B8.1.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=rag-service python3.11 -m unittest discover -s rag-service/tests -v
# In the managed sandbox, use the explicit test-process workaround:
PYTHONDONTWRITEBYTECODE=1 python3.11 scripts/test-inference.py --sandbox-selector-poll
helm template ai-refactor infra/k8s/charts/cloud-cost-compass --namespace cloud-cost-compass
git diff --check
```

The 28 passing tests inject fake SDK/HTTP boundaries and require no third-party packages, network, or live
credentials. They cover policy denial/revocation, wrong region/profile/model,
vector validation/order/concurrency, tenant namespaces, incompatible collections,
actual gateway request shape, Kubernetes planning hints, minimization, provider validation, and escalation.
They do not establish live provider access, SDK integration, tenant authorization,
or deployed ZDR. The restricted workspace also loses asyncio executor-shutdown
wakeups; here the suite was run with a test-only selector wait bound of 50ms.
PyPI DNS is unavailable, so dependency-backed service checks remain unverified.
