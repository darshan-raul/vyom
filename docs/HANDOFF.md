# Current handoff

Updated: 2026-10-11. Latest session: [2026-10-11-01](sessions/2026-10-11-01.md).

## Current state

The separate [Kind chat POC](../poc/kind-chat/README.md) is closed: POC1–POC3 are done. The owner ran it live with OpenRouter and confirmed completion on 2026-10-11; the agent did not observe that run. The POC takes its model key as `OPENROUTER_API_KEY` (Secret key and environment variable), as do the two learning exercises under `poc/`. None of this is sprint delivery.

The main roadmap is still planning only: all S1–S6 tasks are pending and no sprint gate is closed.

## Next action

Start **S1.1** (fresh development scaffold) when the owner asks: mark it in progress, then create new `frontend/` and `backend/` per the constitution and [implementation plan](IMPLEMENTATION_PLAN.md). Prepare **S1.9** next. Do not copy the POC's direct-API design into the S1 agent path; S1 requires LangGraph, the MCP client, the upstream Kubernetes MCP server and the observability stack.

## Limits / environment

Docker 29.7.2, kind 0.31.0, kubectl 1.36.0 and Helm 4.2.2 are installed. Kind clusters `app`, `target` and `lc-basics` existed at session end; they belong to the POC and exercises and can be deleted by the owner.

On 2026-10-11 this machine's IPv4 path to PyPI dropped packets while IPv6 was clean, so `pip install` inside default-bridge Docker builds failed. `docker build --network=host` worked around it. Check this before debugging any S1 image build that fails in pip.

See [tracker](TRACKER.md) for sprint states and [POC decision](DECISIONS.md#separate-local-chat-poc--2026-10-04) for the owner-authorized exception.
