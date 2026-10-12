# Current handoff

Updated: 2026-10-12. Latest session: [2026-10-12-02](sessions/2026-10-12-02.md).

## Current state

**S1.1, S1.9, S1.2 and S1.3 are done and committed to `main`.**

- `backend/` has the evidence contract, trusted context, MCP host and one reviewed tool, `kubernetes__pods_list_in_namespace`. Nothing calls the host from the API yet.
- Kind cluster `vyom` runs the observability stack plus the upstream Kubernetes MCP server v0.0.67 behind `kube-rbac-proxy` v0.23.0 in `vyom`, and demo workloads in `demo` (one Running pod, one in ImagePullBackOff). Details: [MCP_INTEGRATIONS.md](MCP_INTEGRATIONS.md#deployed-on-kind-in-s13).
- `./scripts/mcp-up.sh` installs; `./scripts/mcp-check.sh` verifies live (22 checks).

S1.4–S1.8 are pending and no sprint gate is closed.

## Next action

**S1.4** (initial reasoning adapter) is dependency-ready but blocked on an owner decision: **P01** — which OpenAI-compatible endpoint and model, and how the key is injected (an ignored file is the planned mechanism). Do not ask for the key in chat. Once settled: add the adapter under `backend/src/vyom/agent/`, with `McpHost.tools()` as the source of tool definitions for the real tool-call round trip.

## Unresolved decisions

- **P01**, above.
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
- CI passed on `8931bd4` (S1.1, S1.9); its result on the S1.2/S1.3 commit has not been checked (`gh` is not installed here). `shellcheck` is not installed here.
- This shell is zsh with `cp` aliased to prompt before overwriting: write multi-step checks as bash scripts, use `command cp -f`, and do not put `kubectl run -i` inside a heredoc script (it consumes the rest of the script). Start a `kubectl port-forward` directly, not through a shell function, or `$!` is not kubectl.
- After restarting Tempo, a new trace can take up to about 30 seconds to become queryable. A `kubectl port-forward` to `svc/alloy` dies when the collector pod is replaced.
- Images from GitHub's registry pull slowly from this machine; quay.io pulls took under a minute.
- `npm audit` reports 7 high findings from one `braces` advisory in the `shadcn` CLI dev dependency; `npm audit --omit=dev` reports 0.
- Docker 29.7.2, kind 0.31.0, kubectl 1.36.0 and Helm 4.2.2 are installed.

See [tracker](TRACKER.md) for sprint states.
