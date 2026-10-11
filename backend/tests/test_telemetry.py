import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from vyom import telemetry
from vyom.api.app import app


def _format(**log_kwargs) -> dict:
    record = logging.getLogger("vyom.test").makeRecord(
        "vyom.test", logging.INFO, __file__, 1, "tool call finished", (), **log_kwargs
    )
    return json.loads(telemetry.JsonFormatter().format(record))


def test_log_keeps_allowlisted_fields_and_current_trace_ids():
    with telemetry.tracer_provider().get_tracer("test").start_as_current_span("step") as span:
        entry = _format(
            exc_info=None,
            extra={"operation": "mcp.call", "outcome": "ok", "prompt": "which pods?"},
        )

    assert entry["operation"] == "mcp.call"
    assert entry["outcome"] == "ok"
    assert entry["trace_id"] == format(span.get_span_context().trace_id, "032x")
    assert entry["span_id"] == format(span.get_span_context().span_id, "016x")
    assert "prompt" not in entry


def test_log_records_exception_type_without_its_text():
    try:
        raise ValueError("token=abc123")
    except ValueError as error:
        entry = _format(exc_info=(ValueError, error, error.__traceback__))

    assert entry["error_type"] == "ValueError"
    assert "abc123" not in json.dumps(entry)


def test_metrics_label_route_templates_not_raw_paths():
    client = TestClient(app)
    client.get("/api/health?probe=secret-value")
    client.get("/pods/8f14e45f-secret-id")

    exposition = client.get("/metrics").text

    assert 'vyom_http_requests_total{method="GET",route="/api/health",status="200"}' in exposition
    assert 'vyom_http_requests_total{method="GET",route="unmatched",status="404"}' in exposition
    assert "secret" not in exposition


def test_exported_spans_drop_queries_headers_and_exception_text():
    exported = InMemorySpanExporter()
    telemetry.tracer_provider().add_span_processor(
        SimpleSpanProcessor(telemetry.ScrubbingExporter(exported))
    )
    failing = FastAPI()
    telemetry.instrument(failing)

    @failing.get("/boom")
    def boom():
        raise RuntimeError("upstream said password=hunter2")

    response = TestClient(failing, raise_server_exceptions=False).get(
        "/boom?token=abc123", headers={"Authorization": "Bearer abc123"}
    )

    assert response.status_code == 500
    spans = exported.get_finished_spans()
    assert any(span.name == "GET /boom" for span in spans)
    dumped = "".join(span.to_json() for span in spans)
    assert "abc123" not in dumped
    assert "hunter2" not in dumped
    assert '"exception.type": "RuntimeError"' in dumped
