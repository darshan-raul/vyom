"""Live checks of the direct pod view on Kind, and of its agreement with the MCP path.

Run through scripts/pods-check.sh, which provides the port-forward, the tokens, the API
server's CA and the environment below. Prints one PASS line per check and exits non-zero on
a failure. No credential is printed.
"""

import asyncio
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import generate_latest

from vyom import telemetry
from vyom.api.app import create_app
from vyom.mcp_client.host import McpHost
from vyom.mcp_client.kubernetes import SPECS
from vyom.mcp_client.registry import OperatorConfig

LOCAL = Path(os.environ["VYOM_LOCAL"])
CONTEXT = os.environ["KUBE_CONTEXT"]
CLUSTER_UID = os.environ["VYOM_CLUSTER_UID"]
API_URL = os.environ["VYOM_KUBERNETES_URL"]
API_CA = os.environ["VYOM_KUBERNETES_CA"]
COLLECTOR_TOKEN = os.environ["VYOM_COLLECTOR_TOKEN_FILE"]
MCP_TOKEN = os.environ["VYOM_MCP_TOKEN_FILE"]
MODEL_REF = os.environ.get("VYOM_MODEL_CREDENTIAL_REF", "")
TOOL = "kubernetes__pods_list_in_namespace"
LITERAL_ENV = "vyom-demo-literal-env-value"  # set on the demo `web` pods

Row = tuple[str, str, str, int]


def kubectl(*args: str) -> str:
    command = ["kubectl", "--context", CONTEXT, *args]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def kubectl_pods(namespace: str) -> list[Row]:
    rows = []
    for line in kubectl("-n", namespace, "get", "pods", "--no-headers").splitlines():
        name, ready, status, restarts = line.split()[:4]
        rows.append((name, ready, status, int(restarts)))
    return sorted(rows)


def kubectl_uids(namespace: str) -> dict[str, str]:
    template = '{range .items[*]}{.metadata.name}{" "}{.metadata.uid}{"\\n"}{end}'
    lines = kubectl("-n", namespace, "get", "pods", "-o", f"jsonpath={template}").splitlines()
    return dict(line.split() for line in lines)


def passed(message: str) -> None:
    print(f"PASS  {message}")


def check(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL  {message}")
        sys.exit(1)
    passed(message)


def operator(
    *, namespace="demo", mcp_url=None, api_url=None, collector_token=COLLECTOR_TOKEN
) -> OperatorConfig:
    config = {
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
                "credential_ref": f"file:{MCP_TOKEN}",
                "enabled_tools": ["pods_list_in_namespace"],
                "limits": {"connect_timeout_seconds": 3},
            }
        ],
        "kubernetes": {
            "connection_id": "kind-vyom",
            "url": api_url or API_URL,
            "ca_file": API_CA,
            "credential_ref": f"file:{collector_token}",
            "timeout_seconds": 5,
        },
    }
    if MODEL_REF:
        config["model"] = {
            "provider": os.environ["VYOM_MODEL_PROVIDER"],
            "base_url": os.environ["VYOM_MODEL_BASE_URL"],
            "model": os.environ["VYOM_MODEL"],
            "credential_ref": MODEL_REF,
        }
    return OperatorConfig.model_validate(config)


def request(method: str, path: str, config: OperatorConfig | None = None, **kwargs) -> dict:
    app = create_app(config or operator())

    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://vyom.test") as client:
            return await client.request(method, path, **kwargs)

    response = asyncio.run(send())
    response.raise_for_status()
    return response.json()


def table(config: OperatorConfig | None = None) -> dict:
    return request("GET", "/api/kubernetes/pods", config)["evidence"]


def rows(evidence: dict) -> list[Row]:
    return sorted(
        (
            i["name"],
            i["attributes"]["ready"],
            i["attributes"]["status"],
            i["attributes"]["restarts"],
        )
        for i in evidence["items"]
    )


def error_kinds(evidence: dict) -> list[str]:
    return [error["kind"] for error in evidence["errors"]]


def mcp_evidence() -> dict:
    config = operator()
    evidence = asyncio.run(McpHost(config, SPECS).call(TOOL, None, config.context))
    return evidence.model_dump(mode="json")


def settled_table(attempts: int = 30) -> tuple[dict, list[Row]]:
    """The direct table once it and kubectl agree (pods change state while rolling)."""
    for _ in range(attempts):
        expected, evidence = kubectl_pods("demo"), table()
        if rows(evidence) == expected == kubectl_pods("demo"):
            return evidence, expected
        time.sleep(1)
    return evidence, expected


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
    for name in ("vyom.collector", "vyom.mcp", "vyom.http", "vyom.chat", "vyom.model"):
        logging.getLogger(name).addHandler(handler)
        logging.getLogger(name).setLevel(logging.INFO)
    responses = ""

    # -- The table against kubectl --
    before, expected = settled_table()
    uids = kubectl_uids("demo")
    check(
        before["state"] == "complete"
        and before["source"]["path"] == "direct"
        and before["source"]["collector"] == "kubernetes-pods"
        and before["source"]["mcp"] is None
        and rows(before) == expected,
        f"the direct table equals `kubectl -n demo get pods`: {len(expected)} pods, statuses "
        f"{sorted({row[2] for row in expected})}, state complete",
    )
    check(
        {item["name"]: item["uid"] for item in before["items"]} == uids
        and all(i["id"] == f"k8s:{CLUSTER_UID}:demo:pod:{i['name']}" for i in before["items"]),
        "every row carries the pod's UID as kubectl reports it and the shared resource ID",
    )
    token = Path(COLLECTOR_TOKEN).read_text().strip()
    raw = httpx.get(
        f"{API_URL}/api/v1/namespaces/demo/pods",
        params={"includeObject": "Metadata"},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json;as=Table;g=meta.k8s.io;v=v1",
        },
        verify=API_CA,
    )
    check(
        raw.status_code == 200 and LITERAL_ENV not in raw.text and '"spec"' not in raw.text,
        "what the API server sends the collector has no pod spec and no literal env value "
        f"({len(raw.content)} bytes for {len(expected)} pods)",
    )

    # -- Agreement with the MCP path --
    through_mcp = mcp_evidence()
    check(
        through_mcp["state"] == "complete"
        and through_mcp["source"]["path"] == "mcp"
        and {i["id"]: i["attributes"] for i in through_mcp["items"]}
        == {i["id"]: i["attributes"] for i in before["items"]},
        "the MCP path returns the same resource IDs with the same readiness, status and "
        "restarts as the direct table",
    )

    # -- Independence from MCP --
    without_mcp = table(operator(mcp_url="https://127.0.0.1:9/mcp"))
    check(
        without_mcp["state"] == "complete" and rows(without_mcp) == kubectl_pods("demo"),
        "with the MCP endpoint unreachable the table is still complete and equal to kubectl",
    )

    # -- A controlled workload change, seen by both paths --
    kubectl("-n", "demo", "scale", "deployment/web", "--replicas=2")
    kubectl("-n", "demo", "rollout", "status", "deployment/web", "--timeout=2m")
    after, expected_after = settled_table()
    added = sorted({i["name"] for i in after["items"]} - {i["name"] for i in before["items"]})
    check(
        len(added) == 1
        and rows(after) == expected_after
        and after["collected_at"] > before["collected_at"]
        and after["id"] != before["id"],
        f"after scaling web to 2 replicas the table shows the new pod ({len(expected_after)} "
        "pods, equal to kubectl) in a new collection with a later time",
    )
    new_pod = added[0]
    new_id = f"k8s:{CLUSTER_UID}:demo:pod:{new_pod}"
    through_mcp = mcp_evidence()
    check(
        new_id in {i["id"] for i in through_mcp["items"]}
        and {i["id"]: i["attributes"] for i in through_mcp["items"]}
        == {i["id"]: i["attributes"] for i in after["items"]},
        "a fresh MCP read shows the new pod under the same resource ID, and both paths agree "
        "on every pod",
    )
    answer_start = ""
    if MODEL_REF:
        body = request(
            "POST",
            "/api/chat",
            json={"question": "List every pod in the demo namespace with its status."},
        )
        responses += str(body)
        items = {i["id"] for evidence in body["evidence"] for i in evidence["items"]}
        cited = {citation["item_id"] for citation in body["citations"]}
        check(
            body["outcome"] == "answered"
            and new_pod in body["answer"]
            and new_id in cited
            and cited <= {i["id"] for i in after["items"]}
            and items == {i["id"] for i in after["items"]},
            "a fresh MCP-backed answer names and cites the new pod; every citation is a row of "
            "the direct table"
            + (
                ""
                if body["outcome"] == "answered"
                else f": {body['outcome']} ({body['limitation']})"
            ),
        )
        answer_start = body["answer"][:40]
    else:
        print("NOT RUN  the agent's answer about the changed workload (no model key)")
    kubectl("-n", "demo", "scale", "deployment/web", "--replicas=1")
    kubectl("-n", "demo", "rollout", "status", "deployment/web", "--timeout=2m")
    for _ in range(120):  # the removed pod stays listed as Terminating for its grace period
        if len(kubectl_pods("demo")) == len(expected):
            break
        time.sleep(1)
    restored, expected_restored = settled_table()
    check(
        rows(restored) == expected_restored and len(expected_restored) == len(expected),
        f"after scaling back the table follows: {len(expected_restored)} pods, equal to kubectl",
    )

    # -- Failures are explicit and distinct from an empty namespace --
    denied = table(operator(namespace="kube-system"))
    check(
        denied["state"] == "denied"
        and error_kinds(denied) == ["forbidden"]
        and not denied["items"],
        "a namespace the collector may not read is denied / forbidden, not an empty list",
    )
    bad = table(operator(collector_token=os.environ["VYOM_BAD_TOKEN_FILE"]))
    other = table(operator(collector_token=MCP_TOKEN))
    check(
        bad["state"] == "denied"
        and error_kinds(bad) == ["auth"]
        and other["state"] == "denied"
        and error_kinds(other) == ["auth"],
        "an invalid token, and the token the backend presents to the MCP endpoint, are both "
        "refused by the Kubernetes API: denied / auth",
    )
    unreachable = table(operator(api_url="https://127.0.0.1:9"))
    check(
        unreachable["state"] == "missing" and error_kinds(unreachable) == ["unavailable"],
        "an unreachable API server is missing / unavailable",
    )
    responses += str([before, after, denied, bad, other, unreachable])

    # -- Nothing sensitive in what was emitted or returned --
    spans = exported.get_finished_spans()
    metrics = generate_latest().decode()
    emitted = "".join(span.to_json() for span in spans) + "\n".join(records) + metrics
    leaks = {
        "the collector token": token,
        "the MCP endpoint token": Path(MCP_TOKEN).read_text().strip(),
        "a pod name": expected[0][0],
        "the new pod name": new_pod,
        "a pod UID": next(iter(uids.values())),
        "a literal env value": LITERAL_ENV,
        "the API server address": API_URL.split("//")[1],
        "an answer": answer_start,
    }
    found = [name for name, value in leaks.items() if value and value in emitted]
    check(
        not found
        and 'vyom_collector_runs_total{collector="kubernetes-pods",outcome="ok"}' in metrics
        and 'vyom_collector_runs_total{collector="kubernetes-pods",outcome="forbidden"}' in metrics
        and "vyom_collector_last_success_timestamp_seconds" in metrics,
        f"collector runs, outcomes and last success are in the metrics; no token, pod name, UID, "
        f"env value or API address in {len(spans)} spans, {len(records)} log lines or the "
        "metrics" + (f": {found}" if found else ""),
    )
    secrets = [
        name for name in list(leaks)[:2] + ["a literal env value"] if leaks[name] in responses
    ]
    check(not secrets, "no token or env value in any API response")
    if not MODEL_REF:
        print("INCOMPLETE  re-run with a model key to check the agent's answer")
        sys.exit(2)


if __name__ == "__main__":
    main()
