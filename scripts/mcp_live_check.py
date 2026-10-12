"""Live checks of the Vyom MCP host against the upstream server on Kind.

Run through scripts/mcp-check.sh, which provides the port-forward, the short-lived tokens
and the environment below. Prints one PASS line per check and exits non-zero on a failure.
"""

import asyncio
import json
import logging
import os
import ssl
import subprocess
import sys
from pathlib import Path

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import generate_latest

from vyom import telemetry
from vyom.evidence import ErrorKind, State
from vyom.mcp_client.host import McpHost
from vyom.mcp_client.kubernetes import SPECS
from vyom.mcp_client.registry import OperatorConfig

LOCAL = Path(os.environ["VYOM_LOCAL"])
URL = os.environ["VYOM_MCP_URL"]
CONTEXT = os.environ["KUBE_CONTEXT"]
CLUSTER_UID = os.environ["VYOM_CLUSTER_UID"]
TOOL = "kubernetes__pods_list_in_namespace"
LITERAL_ENV = "vyom-demo-literal-env-value"  # set on the demo `web` pods


def kubectl(*args: str) -> str:
    command = ["kubectl", "--context", CONTEXT, *args]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def passed(message: str) -> None:
    print(f"PASS  {message}")


def check(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL  {message}")
        sys.exit(1)
    passed(message)


def config(*, namespace="demo", token="mcp-token", max_response_bytes=262_144) -> OperatorConfig:
    return OperatorConfig.model_validate(
        {
            "context": {
                "workspace_id": "ws-local",
                "connection_id": "kind-vyom",
                "cluster_uid": CLUSTER_UID,
                "namespace": namespace,
            },
            "mcp_servers": [
                {
                    "id": "kubernetes",
                    "connection_id": "kind-vyom",
                    "url": URL,
                    "ca_file": str(LOCAL / "mcp-tls" / "tls.crt"),
                    "credential_ref": f"file:{LOCAL / token}",
                    "enabled_tools": ["pods_list_in_namespace"],
                    "limits": {"max_response_bytes": max_response_bytes},
                }
            ],
        }
    )


def call(operator_config: OperatorConfig, arguments=None, tool=TOOL):
    host = McpHost(operator_config, SPECS)
    return asyncio.run(host.call(tool, arguments, operator_config.context))


def kinds(evidence) -> list[ErrorKind]:
    return [error.kind for error in evidence.errors]


def kubectl_pods(namespace: str) -> list[tuple[str, str, str, int]]:
    rows = []
    for line in kubectl("-n", namespace, "get", "pods", "--no-headers").splitlines():
        name, ready, status, restarts = line.split()[:4]
        rows.append((name, ready, status, int(restarts)))
    return sorted(rows)


async def raw_upstream() -> tuple[list[str], dict[str, str], str]:
    """Bypass the host's allowlist with a valid credential: what does the server itself allow?"""
    token = (LOCAL / "mcp-token").read_text().strip()
    verify = ssl.create_default_context(cafile=str(LOCAL / "mcp-tls" / "tls.crt"))
    http = httpx2.AsyncClient(
        verify=verify, headers={"Authorization": f"Bearer {token}"}, trust_env=False
    )
    refused = {}
    attempts = {
        "pods_delete": {"namespace": "demo", "name": "web"},
        "pods_exec": {"namespace": "demo", "name": "web", "command": ["env"]},
        "pods_log": {"namespace": "demo", "name": "web"},
        "resources_get": {"apiVersion": "v1", "kind": "Secret", "namespace": "demo", "name": "x"},
        "resources_list": {"apiVersion": "v1", "kind": "Secret", "namespace": "demo"},
        "resources_create_or_update": {"resource": "apiVersion: v1\nkind: ConfigMap"},
    }
    async with http, Client(streamable_http_client(URL, http_client=http), cache=None) as client:
        advertised = [tool.name for tool in (await client.list_tools()).tools]
        for name, arguments in attempts.items():
            try:
                result = await client.call_tool(name, arguments)
                refused[name] = "tool error" if result.is_error else "ALLOWED"
            except Exception as error:
                refused[name] = type(error).__name__
        listing = await client.call_tool("pods_list_in_namespace", {"namespace": "demo"})
        text = "\n".join(getattr(block, "text", "") for block in listing.content)
    return advertised, refused, text


def main() -> None:
    logging.getLogger().setLevel(logging.WARNING)  # keep client-library chatter off the report
    exported = InMemorySpanExporter()
    telemetry.tracer_provider().add_span_processor(
        SimpleSpanProcessor(telemetry.ScrubbingExporter(exported))
    )
    records: list[str] = []
    handler = logging.Handler()
    handler.setFormatter(telemetry.JsonFormatter())
    handler.emit = lambda record: records.append(handler.format(record))
    logging.getLogger("vyom.mcp").addHandler(handler)
    logging.getLogger("vyom.mcp").setLevel(logging.INFO)

    # Handshake and discovery.
    discovery = asyncio.run(McpHost(config(), SPECS).discover("kubernetes"))
    check(
        discovery.error is None and discovery.tools == {TOOL: None} and discovery.not_enabled == 0,
        f"handshake and discovery: protocol {discovery.protocol_version}, upstream "
        f"{discovery.upstream_name!r}, reviewed schema matches, no other tool advertised",
    )

    # Tool call compared with kubectl.
    evidence = call(config())
    mine = sorted(
        (i.name, i.attributes["ready"], i.attributes["status"], i.attributes["restarts"])
        for i in evidence.items
    )
    check(
        evidence.state is State.COMPLETE and mine == kubectl_pods("demo"),
        f"tool call matches `kubectl -n demo get pods`: {len(mine)} pods, "
        f"statuses {sorted({row[2] for row in mine})}, collected {evidence.collected_at:%H:%M:%SZ}",
    )
    check(
        all(item.id == f"k8s:{CLUSTER_UID}:demo:pod:{item.name}" for item in evidence.items),
        "evidence item IDs carry the cluster UID, namespace, kind and name",
    )
    empty = call(config(), {"labelSelector": "app=no-such-app"})
    check(empty.state is State.ZERO and not empty.errors, "a selector matching nothing is `zero`")

    # Endpoint authentication through the host.
    for token, why in (
        ("mcp-token-wrong-audience", "a token for the Kubernetes API audience"),
        ("mcp-token-other-identity", "a ServiceAccount without the endpoint grant"),
    ):
        refused = call(config(token=token))
        check(
            refused.state is State.DENIED and kinds(refused) == [ErrorKind.AUTH],
            f"{why} is refused by the endpoint: denied/auth",
        )

    # Namespace authority.
    proposed = call(config(), {"namespace": "kube-system"})
    check(
        kinds(proposed) == [ErrorKind.SCOPE_VIOLATION],
        "a proposed namespace other than the configured one is refused by the host",
    )
    forbidden = call(config(namespace="kube-system"))
    check(
        forbidden.state is State.DENIED and kinds(forbidden) == [ErrorKind.FORBIDDEN],
        "if the operator configured kube-system, Kubernetes RBAC denies it: denied/forbidden",
    )

    # Writes, exec and Secret reads: host allowlist, then the server itself.
    for tool in ("kubernetes__pods_delete", "kubernetes__pods_exec", "kubernetes__resources_get"):
        refused = call(config(), {"name": "web"}, tool=tool)
        if kinds(refused) != [ErrorKind.TOOL_NOT_ALLOWED]:
            check(False, f"host refuses {tool}")
    passed("host refuses pods_delete, pods_exec and resources_get: tool_not_allowed")
    advertised, refused, raw_table = asyncio.run(raw_upstream())
    check(
        advertised == ["pods_list_in_namespace"] and "ALLOWED" not in refused.values(),
        f"past the host with a valid credential, the server advertises only {advertised} "
        f"and refuses {sorted(refused)}",
    )

    # Oversized result.
    tiny = call(config(max_response_bytes=1024))
    check(
        tiny.state is State.MISSING and kinds(tiny) == [ErrorKind.OVERSIZED] and not tiny.items,
        "with a 1 KiB response limit the exchange is discarded: missing/oversized",
    )

    # Nothing sensitive in evidence or telemetry; the raw table has no env values either.
    token = (LOCAL / "mcp-token").read_text().strip()
    spans = "".join(span.to_json() for span in exported.get_finished_spans())
    metrics = generate_latest().decode()
    haystack = evidence.model_dump_json() + spans + "\n".join(records) + metrics
    names = [item.name for item in evidence.items]
    check(LITERAL_ENV not in raw_table, "the upstream table does not contain the literal env value")
    check(
        LITERAL_ENV not in haystack and token not in haystack,
        "no literal env value or credential in evidence, spans, logs or metrics",
    )
    telemetry_only = spans + "\n".join(records) + metrics
    check(
        not any(name in telemetry_only for name in names) and "kube-system" not in telemetry_only,
        f"no pod name or namespace in {len(exported.get_finished_spans())} spans, "
        f"{len(records)} log lines or the metrics",
    )
    outcomes = sorted({json.loads(line)["outcome"] for line in records})
    passed(f"logged outcomes: {outcomes}")


if __name__ == "__main__":
    main()
