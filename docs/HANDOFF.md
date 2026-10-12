# Current handoff

Updated: 2026-10-12. Latest session: [2026-10-12-04](sessions/2026-10-12-04.md).

## Current state

**S1.1, S1.9, S1.2, S1.3 and S1.4 are done and on `origin/main`. S1.4's live check was run by the owner.**

- `backend/` has the evidence contract, trusted context, MCP host and one reviewed tool, `kubernetes__pods_list_in_namespace`, plus the reasoning adapter `agent/model.py` (LangChain `ChatOpenAI`) for OpenRouter with `anthropic/claude-haiku-5.5`. Nothing calls the host or the adapter from the API yet.
- Kind cluster `vyom` runs the observability stack plus the upstream Kubernetes MCP server v0.0.67 behind `kube-rbac-proxy` v0.23.0 in `vyom`, and demo workloads in `demo` (one Running pod, one in ImagePullBackOff). Details: [MCP_INTEGRATIONS.md](MCP_INTEGRATIONS.md#deployed-on-kind-in-s13).
- `./scripts/mcp-up.sh` installs; `./scripts/mcp-check.sh` verifies live (22 checks).
- `frontend/` is redesigned to the owner's [design spec](design/DESIGN.md) (P11): dark console shell, Today page showing API liveness, and the Ask Vyom panel disabled until the chat route exists. Its §0 says which surface arrives in which sprint.

S1.5–S1.8 are pending and no sprint gate is closed.

## Next action

**S1.5** (bounded graph and MCP-backed chat): propose → host validation → MCP call → normalize → answer, one tool round, through `ModelClient` and `McpHost`, with a chat API route. Its live checks need the model key in the backend's process: an agent session can run them only if the key is in `.local/model-api-key` (mode 600); a variable exported in the owner's terminal is not visible to it. Do not ask for the key in chat. On the UI side, S1.5 enables `frontend/src/components/vyom/ask-vyom.tsx` (remove the disabled state, add the answer with tool, resources and collection time in the right column) and updates the `REASON` and `K8S MCP` cells in `frontend/src/pages/today.tsx` and the ticker's agent state.

## Unresolved decisions

- Sending questions and projected pod names and statuses from the demo cluster to OpenRouter follows from the owner's choice of endpoint but was not separately confirmed ([P01](DECISIONS.md#s14-reasoning-adapter--2026-10-12)).
- UI02–UI04 ([design decisions](DECISIONS.md#frontend-design-spec--2026-10-12)) are the agent's adaptation of the spec to the plan and are proposed, not confirmed: what is left out of the mockups, listing planned surfaces dimmed with their sprint, and the disabled Ask panel.
- MCPC01 (as revised by MCPK01) and MCPC04 are recorded as accepted on the owner's "go ahead"; say so if that reading is wrong.

## Limits / environment

- The live checks ran the host on this machine through a port-forward. The in-cluster path (projected token for `vyom-api` with audience `vyom-mcp`, endpoint certificate as `ca_file`, `https://kubernetes-mcp.vyom.svc:8443/mcp`) is untested until S1.7.
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
- The UI's sprint tags and "not wired / not built" strip cells are static text, not read from the backend; update them in the task that delivers each surface. The UI was checked in Brave headless only; no keyboard or screen-reader pass was done.
- `vyom-design-spec.zip` in the repository root is untracked; its contents are now in `docs/design/`.
- `npm audit` reports 7 high findings from one `braces` advisory in the `shadcn` CLI dev dependency; `npm audit --omit=dev` reports 0.
- Docker 29.7.2, kind 0.31.0, kubectl 1.36.0 and Helm 4.2.2 are installed.

See [tracker](TRACKER.md) for sprint states.
