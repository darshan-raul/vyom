"""Live checks of the chat route: real model, real upstream Kubernetes MCP server on Kind.

Run through scripts/chat-check.sh, which provides the port-forward, the endpoint token, the
model key reference and the environment below. Each case builds the API from an operator
configuration and posts a question to /api/chat in process. Prints one PASS line per check
and exits non-zero on a failure. The key is never printed.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import generate_latest

from vyom import telemetry
from vyom.api.app import create_app
from vyom.credentials import read_credential
from vyom.mcp_client.registry import OperatorConfig

LOCAL = Path(os.environ["VYOM_LOCAL"])
CONTEXT = os.environ["KUBE_CONTEXT"]
CLUSTER_UID = os.environ["VYOM_CLUSTER_UID"]
CREDENTIAL_REF = os.environ["VYOM_MODEL_CREDENTIAL_REF"]
TOOL = "kubernetes__pods_list_in_namespace"
MARKER = "vyom-chat-marker-4482"
LITERAL_ENV = "vyom-demo-literal-env-value"  # set on the demo `web` pods
QUESTION = f"Which pods are unhealthy in the demo namespace? ({MARKER})"


def kubectl(*args: str) -> str:
    command = ["kubectl", "--context", CONTEXT, *args]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def kubectl_pods(namespace: str) -> list[tuple[str, str, str, int]]:
    rows = []
    for line in kubectl("-n", namespace, "get", "pods", "--no-headers").splitlines():
        name, ready, status, restarts = line.split()[:4]
        rows.append((name, ready, status, int(restarts)))
    return sorted(rows)


def passed(message: str) -> None:
    print(f"PASS  {message}")


def check(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL  {message}")
        sys.exit(1)
    passed(message)


def operator(*, namespace="demo", mcp_url=None, model=None) -> OperatorConfig:
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
                    "url": mcp_url or os.environ["VYOM_MCP_URL"],
                    "ca_file": str(LOCAL / "mcp-tls" / "tls.crt"),
                    "credential_ref": f"file:{os.environ['VYOM_MCP_TOKEN_FILE']}",
                    "enabled_tools": ["pods_list_in_namespace"],
                    "limits": {"connect_timeout_seconds": 3},
                }
            ],
            "model": {
                "provider": os.environ["VYOM_MODEL_PROVIDER"],
                "base_url": os.environ["VYOM_MODEL_BASE_URL"],
                "model": os.environ["VYOM_MODEL"],
                "credential_ref": CREDENTIAL_REF,
                **(model or {}),
            },
        }
    )


def ask(question: str, config: OperatorConfig | None = None, **extra) -> tuple[int, dict, str]:
    """POST one question to the API built from ``config``; returns status, body and raw text."""
    app = create_app(config or operator())

    async def post() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://vyom.test") as client:
            return await client.post("/api/chat", json={"question": question, **extra})

    response = asyncio.run(post())
    return response.status_code, response.json(), response.text


def error_kinds(body: dict) -> list[str]:
    return [error["kind"] for evidence in body["evidence"] for error in evidence["errors"]]


def main() -> None:
    logging.getLogger().handlers = []  # the API's JSON log lines are captured below instead
    exported = InMemorySpanExporter()
    telemetry.tracer_provider().add_span_processor(
        SimpleSpanProcessor(telemetry.ScrubbingExporter(exported))
    )
    records: list[str] = []
    handler = logging.Handler()
    handler.setFormatter(telemetry.JsonFormatter())
    handler.emit = lambda record: records.append(handler.format(record))
    for name in ("vyom.chat", "vyom.model", "vyom.mcp", "vyom.http"):
        logging.getLogger(name).addHandler(handler)
        logging.getLogger(name).setLevel(logging.INFO)
    bodies = ""

    # -- The question that closes S1.5 --
    expected = kubectl_pods("demo")
    unhealthy = [name for name, ready, status, _ in expected if status != "Running"]
    healthy = [name for name, _, status, _ in expected if status == "Running"]
    check(bool(unhealthy) and bool(healthy), "kubectl shows a healthy and an unhealthy demo pod")
    status, body, text = ask(QUESTION)
    bodies += text
    limitation = body.get("limitation") or ""
    check(
        status == 200 and body["outcome"] == "answered",
        "a real question is answered through the API, the graph, the model and MCP"
        + ("" if body["outcome"] == "answered" else f": {body['outcome']} ({limitation})"),
    )
    (evidence,) = body["evidence"]
    mine = sorted(
        (
            i["name"],
            i["attributes"]["ready"],
            i["attributes"]["status"],
            i["attributes"]["restarts"],
        )
        for i in evidence["items"]
    )
    collected = datetime.fromisoformat(evidence["collected_at"])
    age = (datetime.now(UTC) - collected).total_seconds()
    upstream = evidence["source"]["mcp"]
    check(
        evidence["source"]["path"] == "mcp"
        and evidence["source"]["mcp"]["tool_id"] == TOOL
        and evidence["state"] == "complete"
        and mine == expected,
        f"the evidence came through {TOOL} (upstream {upstream['upstream_name']} "
        f"{upstream['upstream_version']}), "
        f"is complete and equals `kubectl -n demo get pods`: {len(mine)} pods, collected "
        f"{age:.0f}s ago",
    )
    items = {item["id"]: item["name"] for item in evidence["items"]}
    cited = [items.get(citation["item_id"]) for citation in body["citations"]]
    check(
        all(name in body["answer"] for name in unhealthy)
        and all(name in cited for name in unhealthy)
        and None not in cited
        and all(c["evidence_id"] == evidence["id"] for c in body["citations"]),
        f"the answer names every unhealthy pod and cites it; all {len(cited)} citations "
        "resolve to collected items",
    )
    check(
        all(
            item["id"] == f"k8s:{CLUSTER_UID}:demo:pod:{item['name']}" for item in evidence["items"]
        )
        and evidence["source"]["namespace"] == "demo",
        "evidence carries the configured scope and stable resource IDs",
    )
    trace_id = body["trace_id"]
    spans = [
        s for s in exported.get_finished_spans() if format(s.context.trace_id, "032x") == trace_id
    ]
    names = {span.name for span in spans}
    wanted = {
        "chat.graph",
        "graph.propose",
        "graph.collect",
        "graph.answer",
        "model.client.chat",
        "mcp.client.call",
        "evidence.normalize",
    }
    check(
        wanted <= names,
        f"the response's trace ID finds one trace with the request, graph, model-client and "
        f"MCP-client spans ({len(spans)} spans)"
        + ("" if wanted <= names else f": missing {wanted - names}"),
    )
    answer_start = body["answer"][:40]

    # -- Requests outside what the workflow supports --
    status, body, text = ask(f"What is the capital of France? ({MARKER})")
    bodies += text
    check(
        body["answer"] is None or "Paris" not in body["answer"],
        f"a question the tool cannot ground gets no ungrounded answer: {body['outcome']}",
    )
    status, body, text = ask(f"Delete the broken pod in the demo namespace. ({MARKER})")
    bodies += text
    check(
        body["outcome"] in ("no_tool_used", "answered", "no_evidence")
        and all(kind in ("tool_not_allowed", "invalid_arguments") for kind in error_kinds(body)),
        f"a request to change the cluster makes no change: {body['outcome']}"
        + (f" {error_kinds(body)}" if error_kinds(body) else ""),
    )
    status, body, text = ask(f"Which pods are unhealthy in the kube-system namespace? ({MARKER})")
    bodies += text
    outside = [name for name, *_ in kubectl_pods("kube-system") if name in text]
    check(
        not outside
        and all(e["source"]["namespace"] == "demo" for e in body["evidence"])
        and all(i["namespace"] == "demo" for e in body["evidence"] for i in e["items"]),
        f"a question about another namespace returns nothing from it: {body['outcome']}"
        + (f" {error_kinds(body)}" if error_kinds(body) else ""),
    )
    status, body, text = ask(QUESTION, namespace="kube-system")
    check(status == 422, "a request that carries its own namespace is rejected (422)")

    # -- Integration failures --
    status, body, text = ask(QUESTION, operator(mcp_url="https://127.0.0.1:9/mcp"))
    bodies += text
    check(
        body["outcome"] == "no_evidence"
        and body["answer"] is None
        and error_kinds(body) == ["unavailable"]
        and body["evidence"][0]["state"] == "missing",
        "an unreachable MCP endpoint is reported, not answered: no_evidence / unavailable, "
        "and nothing else was read in its place",
    )
    status, body, text = ask(
        QUESTION.replace("demo", "kube-system"), operator(namespace="kube-system")
    )
    bodies += text
    check(
        body["outcome"] in ("no_evidence", "no_tool_used")
        and body["answer"] is None
        and all(kind == "forbidden" for kind in error_kinds(body)),
        f"a namespace the server identity may not read is a denial, not an empty list: "
        f"{body['outcome']} {error_kinds(body)}",
    )

    # -- Model failures --
    os.environ["VYOM_BOGUS_MODEL_KEY"] = "sk-or-v1-" + "0" * 64
    cases = (
        ("a wrong model key", {"credential_ref": "env:VYOM_BOGUS_MODEL_KEY"}),
        ("a missing model key", {"credential_ref": "file:/nonexistent/vyom-model-api-key"}),
        ("an unreachable model provider", {"base_url": "https://127.0.0.1:9/v1"}),
    )
    for label, change in cases:
        status, body, text = ask(QUESTION, operator(model=change))
        bodies += text
        check(
            status == 200
            and body["outcome"] == "model_unavailable"
            and body["answer"] is None
            and body["evidence"] == [],
            f"{label} is reported, not answered: model_unavailable ({body['limitation']})",
        )

    # -- Nothing sensitive in what was emitted or returned --
    key = read_credential(CREDENTIAL_REF)
    token = Path(os.environ["VYOM_MCP_TOKEN_FILE"]).read_text().strip()
    all_spans = exported.get_finished_spans()
    emitted = (
        "".join(span.to_json() for span in all_spans)
        + "\n".join(records)
        + generate_latest().decode()
    )
    host = os.environ["VYOM_MODEL_BASE_URL"].split("/")[2]
    telemetry_leaks = {
        "the model key": key,
        "the bogus key": os.environ["VYOM_BOGUS_MODEL_KEY"],
        "the endpoint token": token,
        "a question": MARKER,
        "an answer": answer_start,
        "a pod name": unhealthy[0],
        "another pod name": healthy[0],
        "a literal env value": LITERAL_ENV,
        "the model endpoint host": host,
    }
    found = [name for name, value in telemetry_leaks.items() if value and value in emitted]
    check(
        not found,
        f"no key, token, question, answer, pod name, env value or endpoint in {len(all_spans)} "
        f"spans, {len(records)} log lines or the metrics" + (f": {found}" if found else ""),
    )
    response_leaks = {
        "the model key": key,
        "the endpoint token": token,
        "a literal env value": LITERAL_ENV,
        "the model endpoint host": host,
    }
    found = [name for name, value in response_leaks.items() if value in bodies]
    check(
        not found,
        "no key, token, env value or model endpoint in any API response"
        + (f": {found}" if found else ""),
    )
    outcomes = sorted({json.loads(line)["outcome"] for line in records if '"vyom.chat"' in line})
    passed(f"logged chat outcomes: {outcomes}")


if __name__ == "__main__":
    main()
