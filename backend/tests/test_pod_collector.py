"""The direct pod collector and its route against scripted Kubernetes API responses.
Fixture evidence only: scripts/pods-check.sh compares the same path with kubectl on Kind."""

import asyncio
import json
import logging

import httpx
import pytest
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import REGISTRY
from pydantic import ValidationError

from vyom import telemetry
from vyom.api.app import create_app
from vyom.collectors.kubernetes import COLLECTOR, KubernetesApiConfig, PodCollector
from vyom.context import TrustedContext
from vyom.evidence import ErrorKind, ItemDraft, State, build_evidence
from vyom.mcp_client.registry import OperatorConfig

TOKEN = "collector-token-0123"
CONTEXT = TrustedContext(
    workspace_id="ws-local", connection_id="kind-vyom", cluster_uid="c1uster-uid", namespace="demo"
)
COLUMNS = ["Name", "Ready", "Status", "Restarts", "Age", "IP", "Node"]


def row(name, ready, status, restarts, namespace="demo"):
    return {
        "cells": [name, ready, status, restarts, "3h", "10.0.0.9", "node-1"],
        "object": {
            "kind": "PartialObjectMetadata",
            "metadata": {"name": name, "namespace": namespace, "uid": f"uid-{name}"},
        },
    }


def table(*rows, more=None):
    return {
        "kind": "Table",
        "metadata": {"continue": more} if more else {},
        "columnDefinitions": [{"name": name} for name in COLUMNS],
        "rows": list(rows),
    }


WEB = row("web-1", "1/1", "Running", "1 (2h ago)")
BROKEN = row("broken-1", "0/1", "ImagePullBackOff", "0")


@pytest.fixture
def config(monkeypatch) -> KubernetesApiConfig:
    monkeypatch.setenv("VYOM_TEST_COLLECTOR_TOKEN", TOKEN)
    return KubernetesApiConfig(
        connection_id="kind-vyom",
        url="https://kubernetes.test",
        credential_ref="env:VYOM_TEST_COLLECTOR_TOKEN",
    )


def collect(config, respond, *, context=CONTEXT):
    """Run one collection against ``respond``; returns the evidence and the requests sent."""
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        answer = respond(request) if callable(respond) else respond
        return httpx.Response(200, json=answer) if isinstance(answer, dict) else answer

    collector = PodCollector(config, transport=httpx.MockTransport(handler))
    return asyncio.run(collector.collect(context)), sent


def kinds(evidence):
    return [error.kind for error in evidence.errors]


def test_pods_are_read_page_by_page_as_a_table_with_metadata_only(config):
    pages = iter([table(WEB, more="next-page"), table(BROKEN)])

    evidence, sent = collect(config, lambda _request: next(pages))

    assert evidence.state is State.COMPLETE and evidence.coverage.returned == 2
    assert evidence.source.path == "direct" and evidence.source.collector == COLLECTOR
    assert evidence.source.mcp is None and evidence.source.namespace == "demo"
    assert [(item.id, item.uid, item.attributes) for item in evidence.items] == [
        (
            "k8s:c1uster-uid:demo:pod:web-1",
            "uid-web-1",
            {"ready": "1/1", "status": "Running", "restarts": 1},
        ),
        (
            "k8s:c1uster-uid:demo:pod:broken-1",
            "uid-broken-1",
            {"ready": "0/1", "status": "ImagePullBackOff", "restarts": 0},
        ),
    ]
    first, second = sent
    assert first.url.path == "/api/v1/namespaces/demo/pods"  # namespace from the context
    assert first.url.params["includeObject"] == "Metadata" and "as=Table" in first.headers["accept"]
    assert first.headers["authorization"] == f"Bearer {TOKEN}"
    assert second.url.params["continue"] == "next-page"
    # Columns Vyom does not keep (IP, node) are not in the evidence.
    assert "10.0.0.9" not in evidence.model_dump_json()


def test_items_have_the_same_identity_as_the_mcp_path(config):
    evidence, _ = collect(config, table(WEB))
    mcp = build_evidence(
        context=CONTEXT, path="mcp", drafts=[ItemDraft(kind="Pod", namespace="demo", name="web-1")]
    )

    assert evidence.items[0].id == mcp.items[0].id


def test_an_empty_namespace_is_zero_not_missing(config):
    evidence, _ = collect(config, table())

    assert evidence.state is State.ZERO and evidence.errors == ()


@pytest.mark.parametrize(
    ("response", "kind", "state"),
    [
        (httpx.Response(403, json={"message": "pods is forbidden"}), ErrorKind.FORBIDDEN, "denied"),
        (httpx.Response(401, json={"message": "Unauthorized"}), ErrorKind.AUTH, "denied"),
        (httpx.Response(503, text="apiserver-detail-55"), ErrorKind.UNAVAILABLE, "missing"),
        (httpx.Response(200, text="not json"), ErrorKind.INVALID_OUTPUT, "missing"),
        ({"kind": "Table", "rows": [{"cells": []}]}, ErrorKind.INVALID_OUTPUT, "missing"),
        (httpx.Response(200, content=b"x" * 2_000_000), ErrorKind.OVERSIZED, "missing"),
    ],
)
def test_failures_are_explicit_and_distinct(config, response, kind, state):
    evidence, _ = collect(config, response)

    assert kinds(evidence) == [kind] and evidence.state.value == state
    assert evidence.items == () and "apiserver-detail-55" not in evidence.model_dump_json()


def test_unreachable_api_slow_api_and_unreadable_token(config):
    def refuse(_request):
        raise httpx.ConnectError("refused")

    def stall(_request):
        raise httpx.ReadTimeout("slow")

    assert kinds(collect(config, refuse)[0]) == [ErrorKind.UNAVAILABLE]
    assert kinds(collect(config, stall)[0]) == [ErrorKind.TIMEOUT]
    absent = config.model_copy(update={"credential_ref": "env:VYOM_NO_SUCH_TOKEN"})
    evidence, sent = collect(absent, table(WEB))
    assert kinds(evidence) == [ErrorKind.AUTH] and sent == []


def test_scope_is_the_trusted_context(config):
    other = CONTEXT.model_copy(update={"connection_id": "another-cluster"})
    evidence, sent = collect(config, table(WEB), context=other)
    assert kinds(evidence) == [ErrorKind.SCOPE_VIOLATION] and sent == []

    # An API that answers with another namespace's pods is not believed.
    evidence, _ = collect(config, table(row("etcd", "1/1", "Running", "0", "kube-system")))
    assert kinds(evidence) == [ErrorKind.SCOPE_VIOLATION] and evidence.items == ()


def test_a_failed_later_page_and_the_item_limit_leave_partial_evidence(config):
    pages = iter([table(WEB, more="next-page"), httpx.Response(500)])
    evidence, _ = collect(config, lambda _request: next(pages))
    assert evidence.state is State.PARTIAL and kinds(evidence) == [ErrorKind.UNAVAILABLE]
    assert [item.name for item in evidence.items] == ["web-1"]

    small = config.model_copy(update={"max_items": 1})
    evidence, _ = collect(small, table(WEB, BROKEN))
    assert evidence.state is State.PARTIAL and evidence.coverage.truncated
    assert kinds(evidence) == [ErrorKind.TRUNCATED] and len(evidence.items) == 1


def test_configuration_takes_an_api_root_and_a_credential_reference_only():
    base = {"connection_id": "kind-vyom", "credential_ref": "env:TOKEN"}
    for url in ("http://kubernetes.test", "https://u:p@kubernetes.test", "https://k.test/api/v1"):
        with pytest.raises(ValidationError):
            KubernetesApiConfig(url=url, **base)
    with pytest.raises(ValidationError) as raised:
        KubernetesApiConfig(url="https://kubernetes.test", connection_id="c", credential_ref=TOKEN)
    assert TOKEN not in str(raised.value)


def test_collector_telemetry_has_no_resource_names(config):
    exported = InMemorySpanExporter()
    processor = SimpleSpanProcessor(telemetry.ScrubbingExporter(exported))
    telemetry.tracer_provider().add_span_processor(processor)
    lines: list[str] = []
    handler = logging.Handler()
    handler.setFormatter(telemetry.JsonFormatter())
    handler.emit = lambda record: lines.append(handler.format(record))
    logger = logging.getLogger("vyom.collector")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    labels = {"collector": COLLECTOR, "outcome": "forbidden"}
    before = REGISTRY.get_sample_value("vyom_collector_runs_total", labels) or 0

    try:
        collect(config, table(WEB, BROKEN))
        collect(config, httpx.Response(403))
    finally:
        logger.removeHandler(handler)
        processor.shutdown()

    spans = exported.get_finished_spans()
    assert {"collector.kubernetes.pods", "evidence.normalize"} <= {span.name for span in spans}
    assert [json.loads(line)["outcome"] for line in lines] == ["ok", "forbidden"]
    assert REGISTRY.get_sample_value("vyom_collector_runs_total", labels) == before + 1
    last = {"collector": COLLECTOR}
    assert REGISTRY.get_sample_value("vyom_collector_last_success_timestamp_seconds", last) > 0
    emitted = "".join(span.to_json() for span in spans) + "\n".join(lines)
    for payload in ("web-1", "broken-1", "uid-web-1", TOKEN, "kubernetes.test"):
        assert payload not in emitted


def get_pods(app):
    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://vyom.test") as client:
            return await client.get("/api/kubernetes/pods")

    return asyncio.run(send())


def test_pods_route_does_not_depend_on_mcp_or_the_model(config):
    # MCP endpoint and model are configured but unreachable; the table must not care.
    operator = OperatorConfig.model_validate(
        {
            "context": CONTEXT.model_dump(),
            "mcp_servers": [
                {
                    "id": "kubernetes",
                    "connection_id": "kind-vyom",
                    "url": "https://127.0.0.1:9/mcp",
                    "credential_ref": "env:VYOM_NO_SUCH_TOKEN",
                    "enabled_tools": ["pods_list_in_namespace"],
                }
            ],
            "kubernetes": config.model_dump(),
        }
    )
    collector = PodCollector(
        config, transport=httpx.MockTransport(lambda _: httpx.Response(200, json=table(WEB)))
    )

    response = get_pods(create_app(operator, pods=collector))

    body = response.json()
    assert response.status_code == 200 and body["configured"] is True
    assert (
        body["evidence"]["state"] == "complete" and body["evidence"]["source"]["path"] == "direct"
    )
    assert body["evidence"]["items"][0]["name"] == "web-1" and TOKEN not in response.text

    unconfigured = get_pods(create_app(None)).json()
    assert unconfigured == {"configured": False, "evidence": None}
