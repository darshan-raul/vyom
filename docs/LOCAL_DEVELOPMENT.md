# Local development and deployment

Current implementation: live pod table and bounded MCP-backed questions, with no Postgres inventory yet. See [tracker](TRACKER.md) for delivery status and [handoff](HANDOFF.md) for next work.

## Kind profiles

Create the local cluster with `kind create cluster --config deploy/kind/cluster.yaml`. Scripts default to `kind-vyom`; set `KUBE_CONTEXT` explicitly for a different context. Never infer permission to use a non-local cluster.

Application only (no telemetry stores or Prometheus CRDs required):

```sh
VYOM_TELEMETRY=none ./scripts/vyom-up.sh
./scripts/vyom-check.sh
./scripts/vyom-forward.sh
```

Prometheus with Kubernetes health metrics, without Grafana, Loki, Tempo or Alloy:

```sh
VYOM_TELEMETRY=metrics ./scripts/observability-up.sh
VYOM_TELEMETRY=metrics ./scripts/vyom-up.sh
./scripts/vyom-check.sh
```

Full optional telemetry stack and historical telemetry gates:

```sh
VYOM_TELEMETRY=full ./scripts/observability-up.sh
VYOM_TELEMETRY=full ./scripts/vyom-up.sh
./scripts/vyom-check.sh
./scripts/observability-check.sh
./scripts/s18-gate.sh
```

`vyom-up.sh` defaults to `none`; `observability-up.sh` defaults to `metrics`. The application gate reads the installed ServiceMonitor setting: it checks Prometheus when enabled and explicitly reports SKIP when disabled. The full telemetry gates require the full profile and are not minimal-install gates. Missing ServiceMonitor CRDs cause a metrics/full application install to fail with installation instructions.

Changing profiles does not uninstall existing Loki/Tempo/Alloy releases or erase their data. Installing the metrics profile disables Grafana in the Prometheus release. Use a fresh local cluster to verify absence of optional stores. Chart defaults disable ServiceMonitor and trace export; `/metrics` and sanitized application logs remain available.

Set the model key through a private `VYOM_MODEL_KEY_FILE` (default `.local/model-api-key`) or `OPENROUTER_API_KEY`. Never commit it. Without a key, the direct pod view still works and questions report an unavailable model. The UI is accessible only through localhost port-forwarding. The scripts build and load local images and deploy read-only collection identities; lab/bootstrap commands themselves create local resources.

For development without building images, see `scripts/dev-up.sh` and the [frontend study guide](../learning/frontend-console.md). The existing live scripts and [MCP integration guide](MCP_INTEGRATIONS.md) document the current bounded pod capability. [Observability](OBSERVABILITY.md) describes full-stack instrumentation and historical gates.
