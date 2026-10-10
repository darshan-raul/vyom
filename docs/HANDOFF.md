# Current handoff

Updated: 2026-10-10. Latest session: [2026-10-10-01](sessions/2026-10-10-01.md).

## Current state

The separate [Kind chat POC](../poc/kind-chat/README.md) at `poc/kind-chat/` is code-complete and has not been run live. The owner is driving the live run (POC3, in progress) with OpenRouter and `anthropic/claude-haiku-5.5`. The main roadmap remains planning only; all S1–S6 tasks are pending and no sprint gate is closed.

This session regenerated `frontend/package-lock.json`: the committed one failed `npm ci` with `Invalid Version`, which would have broken the UI image build. The README gained a request-path section, a check after each step, OpenRouter values and failure experiments. These changes are uncommitted.

## Next action

Owner: follow the POC README from `poc/kind-chat/`, steps 1–6. The step-6 `curl /api/chat` returning `"status":"ok"` with two `complete` sources closes POC3; record the result in the tracker. `/api/health` only proves startup configuration. Renew an expired target token (requested lifetime one hour); restart the API after model key rotation.

When main-roadmap implementation is requested, start **S1.1**, then prepare **S1.9**, following the constitution and implementation plan. Do not treat this direct-API POC as delivery of the required LangGraph/MCP/observability stack.

## Limits / environment

Checks run: backend `pytest -q` (14 passed, Python 3.14.6, plain pytest with no harness) and frontend clean `npm ci` + typecheck/build (Node 26.1.0). Not run: image builds (including `npm ci` inside `node:22-alpine`), chart lint/render, any cluster or browser step, any model call. Kind cross-cluster routing, target TLS certificate coverage, image startup and OpenRouter compatibility await the owner's run. Docker, kind 0.31.0, kubectl 1.36.0 and Helm 4.2.2 are installed; no Kind clusters existed at session end.

See [tracker](TRACKER.md) for sprint states and [POC decision](DECISIONS.md#separate-local-chat-poc--2026-10-04) for the owner-authorized exception.
