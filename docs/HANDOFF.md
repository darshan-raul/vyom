# Current handoff

Updated: 2026-10-13. Latest session: [2026-10-13-01](sessions/2026-10-13-01.md).

## Current state

**S1.1–S1.5 and S1.9 are done. S1.5's live gate was run by the owner on 2026-10-13. S1.1–S1.4 are on `origin/main`; S1.5 and the `poc/` → `learning/` rename are not committed.**

- `backend/` now answers a question end to end: `POST /api/chat` runs the LangGraph workflow in `agent/graph.py` (propose → one tool call through `McpHost` → answer with checked citations) and `GET /api/agent` reports what is configured. The API loads the operator file named by `VYOM_CONFIG`; without it chat answers `not_configured`. Detail: [MCP_INTEGRATIONS.md](MCP_INTEGRATIONS.md#chat-workflow-in-s15).
- `frontend/` follows the owner's [design spec](design/DESIGN.md). The Ask Vyom panel is live: it sends only the question and shows the answer, citations, tool, evidence items, collection time and trace ID, or the fixed reason there is no answer.
- `./scripts/chat-up.sh` runs the backend on this machine against Kind for development; `./scripts/chat-check.sh` is the S1.5 live gate.
- Kind cluster `vyom` runs the observability stack plus the upstream Kubernetes MCP server v0.0.67 behind `kube-rbac-proxy` v0.23.0 in `vyom`, and demo workloads in `demo` (one Running pod, one in ImagePullBackOff). Details: [MCP_INTEGRATIONS.md](MCP_INTEGRATIONS.md#deployed-on-kind-in-s13).

S1.6–S1.8 are pending and no sprint gate is closed.

## Next action

**S1.6** (direct Kubernetes evidence view): a direct-SDK pod collector with its own scoped identity behind the same evidence contract, an API route, and the Kubernetes surface in the UI ([DESIGN.md §0](design/DESIGN.md)). It must keep working with MCP down, and a controlled workload change must show in both the table and a fresh MCP-backed answer with matching resource identity.

## Unresolved decisions

- Sending questions and projected pod names and statuses from the demo cluster to OpenRouter follows from the owner's choice of endpoint but was not separately confirmed ([P01](DECISIONS.md#s14-reasoning-adapter--2026-10-12)).
- CHAT01–CHAT05 ([chat decisions](DECISIONS.md#s15-bounded-graph-and-chat--2026-10-13)) are implementation choices made without the owner's view; CHAT02 (an uncited answer is withheld, not shown with a warning) and CHAT03 (every outcome is HTTP 200 with an explicit `outcome`) are the ones most worth a look.
- UI02–UI04 ([design decisions](DECISIONS.md#frontend-design-spec--2026-10-12)) are the agent's adaptation of the spec to the plan and are proposed, not confirmed: what is left out of the mockups, listing planned surfaces dimmed with their sprint, and the disabled Ask panel.
- MCPC01 (as revised by MCPK01) and MCPC04 are recorded as accepted on the owner's "go ahead"; say so if that reading is wrong.

## Limits / environment

- The live checks ran the host and the API on this machine through a port-forward. The in-cluster path (projected token for `vyom-api` with audience `vyom-mcp`, endpoint certificate as `ca_file`, `https://kubernetes-mcp.vyom.svc:8443/mcp`) is untested until S1.7.
- The MCP pod's ServiceAccount holds cluster-scoped `create` on `tokenreviews` and `subjectaccessreviews` for the proxy. `/healthz` is unauthenticated through the proxy; authenticated callers can also reach the server's `/metrics` and `/stats`.
- The endpoint certificate in `.local/mcp-tls/` is self-signed and valid 90 days from 2026-10-12; renew by deleting the directory and re-running `scripts/mcp-up.sh`. Token rotation was not exercised.
- The upstream pod table has no UID and no continuation marker: items are identified by namespace/kind/name and a returned list is treated as complete. A changed table layout fails as `invalid_output`.
- An upstream upgrade that changes the tool's input schema disables the tool until `kubernetes.py` is reviewed and its digest updated.
- Upstream MCP logs are collected (the pod is in `vyom`). Keep `log_level` below 6 in `config.toml`.
- Upstream metrics and tracing are not enabled; MCP panels are not on the second dashboard; Prometheus does not scrape the backend until S1.7.
- Records from the `mcp` and HTTP client loggers are dropped by design; debug an MCP exchange with `scripts/mcp_live_check.py` or a test.
- CI passed on `8931bd4`; its results on `6461441` and on the S1.4 commit have not been checked (`gh` is not installed here).
- The adapter makes one request with no retries and does not stream. It disables LangSmith export per request; do not set `OPENAI_ORG_ID` in the backend's environment (the `openai` client would send it as a header). `scripts/model-check.sh` spends a few thousand tokens per run.
- In the S1.4 live check the tool result was canned, not from MCP. The model would not send arguments outside the offered schema, so the host's refusal of those is offline evidence only.
- This shell is zsh with `cp` aliased to prompt before overwriting: write multi-step checks as bash scripts, use `command cp -f`, and do not put `kubectl run -i` inside a heredoc script (it consumes the rest of the script). Start a `kubectl port-forward` directly, not through a shell function, or `$!` is not kubectl.
- After restarting Tempo, a new trace can take up to about 30 seconds to become queryable. A `kubectl port-forward` to `svc/alloy` dies when the collector pod is replaced.
- Images from GitHub's registry pull slowly from this machine; quay.io pulls took under a minute.
- In the S1.5 live run the model cited correctly and declined the ungroundable, change and other-namespace questions without calling the tool. Injected tool text, a second tool round, an uncited answer and the 60 s deadline did not occur live and are proven offline only.
- The chat has no history: one question, one answer, nothing stored (history is S3). The answer is shown as plain text; Markdown from the model is not rendered.
- `GET /api/agent` reports configuration only; it does not probe the model or MCP. The UI's strip cells for those turn nominal or failed only after a question.
- The chat metrics have no dashboard panels yet, and Prometheus does not scrape the backend until S1.7.
- `scripts/chat-up.sh` writes `.local/operator.json` and a one-hour endpoint token (`.local/dev-mcp-token`, removed on exit); restart it when chat starts reporting an auth failure.
- The UI's sprint tags and "not built" strip cells are static text, not read from the backend; update them in the task that delivers each surface. The UI was checked in Brave headless only; no keyboard or screen-reader pass was done.
- `poc/` was renamed to `learning/` on 2026-10-12 at the owner's request; older session records still name the old path. The three `.venv` directories under it were created at the old path, so recreate them before running anything there. `learning/mcp+observability-bootstrap.md` is the owner's study guide for S1.1–S1.4, moved out of `.local/`.
- `vyom-design-spec.zip` in the repository root is untracked; its contents are now in `docs/design/`.
- `npm audit` reports 7 high findings from one `braces` advisory in the `shadcn` CLI dev dependency; `npm audit --omit=dev` reports 0.
- Docker 29.7.2, kind 0.31.0, kubectl 1.36.0 and Helm 4.2.2 are installed.

See [tracker](TRACKER.md) for sprint states.
