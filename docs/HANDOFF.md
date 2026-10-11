# Current handoff

Updated: 2026-10-11. Latest session: [2026-10-11-03](sessions/2026-10-11-03.md).

## Current state

**S1.1 and S1.9 are done and committed to `main`.**

- `frontend/` shows one Backend health card. `backend/` serves `GET /api/health` and `/metrics`, has the `mcp_client` builder and `telemetry.py` (allowlisted JSON logs, bounded request metrics, scrubbed OTLP traces). `agent/` and `collectors/` are empty packages.
- The observability stack installs on Kind from `deploy/observability/` with `scripts/observability-up.sh` and is verified by `scripts/observability-check.sh`. Details and limits: [OBSERVABILITY.md](OBSERVABILITY.md#installed-on-kind-in-s19).
- Kind cluster `vyom` (context `kind-vyom`) was left running with the stack at session end.

All other S1 tasks are pending and no sprint gate is closed. The [Kind chat POC](../poc/kind-chat/README.md) is closed and is not sprint delivery.

## Next action

Start **S1.2** (evidence, MCP client and trusted context). Add its spans, metrics and logs through `vyom.telemetry`; extend `LOG_FIELDS` deliberately for server and tool IDs. Do not copy the POC's direct-API design into the S1 agent path.

## Limits / environment

- Prometheus does not scrape the backend yet; that needs the Vyom chart and a ServiceMonitor in S1.7. Prometheus already selects ServiceMonitors from any release.
- The second dashboard has no graph, model or MCP panels; add each with the metric it shows.
- Dashboards and the log/trace links were checked through APIs, not in the Grafana UI. No real chat trace exists.
- PVC sizes are not enforced on Kind ([OBS05](DECISIONS.md#s19-observability-pins-and-deviations--2026-10-11), proposed).
- Add the upstream MCP server's logs to the collector allowlist only after S1.3 confirms they are payload-free; the demo namespace is deliberately not collected.
- After restarting Tempo, a new trace can take up to about 30 seconds to become queryable.
- A `kubectl port-forward` to `svc/alloy` dies when the collector pod is replaced; restart it before sending spans.
- Images hosted on GitHub's registry pull slowly from this machine (one small image took about four minutes); a clean stack install took 16 minutes. `pkill -f` patterns can match the calling shell's own command line.
- The CI workflow first runs on the push of this work; its result was not checked in session 2026-10-11-03.
- `npm audit` reports 7 high findings from one `braces` advisory in the `shadcn` CLI dev dependency; `npm audit --omit=dev` reports 0.
- MCP SDK 2.3.0 raises transport failures as an `ExceptionGroup`; S1.2 must normalize them.
- Docker 29.7.2, kind 0.31.0, kubectl 1.36.0 and Helm 4.2.2 are installed.

See [tracker](TRACKER.md) for sprint states.
