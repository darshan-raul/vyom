#!/usr/bin/env bash
# Open the Vyom UI at http://127.0.0.1:8080 through a localhost-only port-forward.
# Grafana has its own forward: see scripts/observability-up.sh.
#   KUBE_CONTEXT  kubectl context (default: kind-vyom)   UI_PORT (8080)
set -euo pipefail
exec kubectl --context "${KUBE_CONTEXT:-kind-vyom}" -n vyom port-forward --address 127.0.0.1 \
  service/vyom-ui "${UI_PORT:-8080}:8080"
