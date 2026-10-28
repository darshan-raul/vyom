"""Runs inside the Vyom API pod (piped in by scripts/vyom-check.sh): the in-cluster MCP path.

Loads the operator file the pod was given, discovers the upstream Kubernetes MCP server with
the pod's own projected token and certificate, and calls the one enabled tool. Prints one JSON
object with names and states only: no token, no URL.
"""

import asyncio
import json
import os

from vyom.mcp_client.host import McpHost
from vyom.mcp_client.kubernetes import SPECS
from vyom.mcp_client.registry import load_operator_config

operator = load_operator_config(os.environ["VYOM_CONFIG"])
host = McpHost(operator, SPECS)


async def main() -> dict:
    discovery = await host.discover("kubernetes")
    evidence = await host.call("kubernetes__pods_list_in_namespace", None, operator.context)
    return {
        "discovery_error": discovery.error and discovery.error.value,
        "tools": {name: problem and problem.value for name, problem in discovery.tools.items()},
        "upstream": evidence.source.mcp and evidence.source.mcp.upstream_name,
        "state": evidence.state.value,
        "path": evidence.source.path,
        "errors": [error.kind.value for error in evidence.errors],
        "pods": sorted(f"{item.namespace}/{item.name}" for item in evidence.items),
    }


print(json.dumps(asyncio.run(main())))
