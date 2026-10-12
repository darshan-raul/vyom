"""Payload-free telemetry for the backend: JSON logs, Prometheus metrics and OTLP traces.

Rules every caller relies on:
- Logs carry a constant message plus fields from ``LOG_FIELDS`` only; anything else is dropped.
- Metric labels are bounded: route templates, known methods and status codes, configured MCP
  server and tool IDs, the configured model provider and model, and fixed outcome names.
- Spans never export URL queries, headers or exception text.
- Export is asynchronous and bounded; a telemetry outage costs spans, never a request.
"""

import json
import logging
import os
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, Request, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from vyom import __version__

SERVICE_NAME = "vyom-api"

# ---- Logs ----------------------------------------------------------------------------

# The only structured fields a log call may add. Extend deliberately; never add free text,
# prompts, answers, tool bodies, headers, URLs with queries or exception messages.
LOG_FIELDS = frozenset(
    {
        "operation",
        "outcome",
        "duration_ms",
        "http_method",
        "http_route",
        "http_status",
        "error_type",
        # Configured IDs only; a tool name a model made up is logged as "unlisted".
        "mcp_server",
        "mcp_tool",
        # From operator configuration, never from a request or a reply.
        "collector",  # a collector's fixed name
        "model_provider",
        "model_name",
        # Provider-reported counts; the fields are absent when the provider reported none.
        "input_tokens",
        "output_tokens",
    }
)

# Client libraries log free text (endpoint URLs, upstream error bodies). Their records are
# dropped; the owning Vyom module logs the same event with allowlisted fields instead.
_SILENCED_LOGGERS = (
    "mcp",
    "httpx2",
    "httpcore2",
    "httpx",
    "httpcore",
    "openai",
    "langchain",
    "langchain_core",
    "langchain_openai",
    "langgraph",
    "langsmith",
)


def _owned_or_safe(record: logging.LogRecord) -> bool:
    return not any(
        record.name == name or record.name.startswith(name + ".") for name in _SILENCED_LOGGERS
    )


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "service": SERVICE_NAME,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = trace.get_current_span().get_span_context()
        if context.is_valid:
            entry["trace_id"] = format(context.trace_id, "032x")
            entry["span_id"] = format(context.span_id, "016x")
        for field in LOG_FIELDS:
            if field in record.__dict__:
                entry[field] = record.__dict__[field]
        if record.exc_info and record.exc_info[0] is not None:
            # The exception type only: messages and tracebacks can carry payloads.
            entry.setdefault("error_type", record.exc_info[0].__name__)
        return json.dumps(entry, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(_owned_or_safe)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    # uvicorn's access log prints raw request lines with query strings; requests are logged
    # by the middleware below with the route template instead.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


# ---- Metrics -------------------------------------------------------------------------

_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_UNOBSERVED_ROUTES = frozenset({"/metrics", "/api/health"})  # probes and scrapes: no log, no span

HTTP_REQUESTS = Counter(
    "vyom_http_requests_total", "HTTP requests handled.", ["method", "route", "status"]
)
HTTP_DURATION = Histogram(
    "vyom_http_request_duration_seconds", "HTTP request duration.", ["method", "route"]
)

_log = logging.getLogger("vyom.http")


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", None) or "unmatched"


async def _observe_request(request: Request, call_next) -> Response:
    method = request.method if request.method in _METHODS else "OTHER"
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        duration = time.perf_counter() - started
        route = _route_template(request)
        HTTP_REQUESTS.labels(method, route, str(status)).inc()
        HTTP_DURATION.labels(method, route).observe(duration)
        if route not in _UNOBSERVED_ROUTES:
            _log.info(
                "request handled",
                extra={
                    "operation": "http.request",
                    "outcome": "error" if status >= 500 else "ok",
                    "duration_ms": round(duration * 1000, 1),
                    "http_method": method,
                    "http_route": route,
                    "http_status": status,
                },
            )


MCP_OPERATIONS = Counter(
    "vyom_mcp_client_operations_total",
    "MCP client operations by configured server and tool.",
    ["server", "tool", "operation", "outcome"],
)
MCP_DURATION = Histogram(
    "vyom_mcp_client_operation_duration_seconds",
    "MCP client operation duration.",
    ["server", "tool", "operation"],
)

_mcp_log = logging.getLogger("vyom.mcp")


def record_mcp_operation(
    operation: str,
    *,
    server: str,
    tool: str,
    outcome: str,
    duration: float,
    error_type: str | None = None,
) -> None:
    """Count, time and log one MCP client operation.

    ``server`` and ``tool`` must already be bounded to configured IDs by the caller, and
    ``outcome`` to ``ok`` or an error kind. Arguments and results are never passed here.
    """
    MCP_OPERATIONS.labels(server, tool, operation, outcome).inc()
    MCP_DURATION.labels(server, tool, operation).observe(duration)
    fields: dict[str, object] = {
        "operation": f"mcp.{operation}",
        "outcome": outcome,
        "duration_ms": round(duration * 1000, 1),
        "mcp_server": server,
        "mcp_tool": tool,
    }
    if error_type is not None:
        fields["error_type"] = error_type
    _mcp_log.log(
        logging.INFO if outcome == "ok" else logging.WARNING,
        "mcp operation finished",
        extra=fields,
    )


MODEL_REQUESTS = Counter(
    "vyom_model_requests_total",
    "Requests to the reasoning endpoint by configured provider and model.",
    ["provider", "model", "outcome"],
)
MODEL_DURATION = Histogram(
    "vyom_model_request_duration_seconds",
    "Reasoning endpoint request duration.",
    ["provider", "model"],
    buckets=(0.25, 0.5, 1, 2, 5, 10, 20, 30, 60, 120),
)
MODEL_TOKENS = Counter(
    "vyom_model_tokens_total",
    "Tokens as reported by the provider. Replies without a report add nothing here.",
    ["provider", "model", "direction"],
)
MODEL_USAGE_UNAVAILABLE = Counter(
    "vyom_model_usage_unavailable_total",
    "Successful replies for which the provider reported no token usage.",
    ["provider", "model"],
)

_model_log = logging.getLogger("vyom.model")


def record_model_request(
    *,
    provider: str,
    model: str,
    outcome: str,
    duration: float,
    usage: tuple[int, int] | None,
    error_type: str | None = None,
) -> None:
    """Count, time and log one request to the reasoning endpoint.

    ``provider`` and ``model`` come from operator configuration and ``outcome`` is ``ok`` or
    an error kind. ``usage`` is (input, output) tokens as reported, or None when the provider
    reported none: unavailable, not zero. Messages and replies are never passed here.
    """
    MODEL_REQUESTS.labels(provider, model, outcome).inc()
    MODEL_DURATION.labels(provider, model).observe(duration)
    fields: dict[str, object] = {
        "operation": "model.chat",
        "outcome": outcome,
        "duration_ms": round(duration * 1000, 1),
        "model_provider": provider,
        "model_name": model,
    }
    if usage is not None:
        MODEL_TOKENS.labels(provider, model, "input").inc(usage[0])
        MODEL_TOKENS.labels(provider, model, "output").inc(usage[1])
        fields["input_tokens"], fields["output_tokens"] = usage
    elif outcome == "ok":
        MODEL_USAGE_UNAVAILABLE.labels(provider, model).inc()
    if error_type is not None:
        fields["error_type"] = error_type
    _model_log.log(
        logging.INFO if outcome == "ok" else logging.WARNING,
        "model request finished",
        extra=fields,
    )


CHAT_REQUESTS = Counter(
    "vyom_chat_requests_total", "Chat questions by how they ended.", ["outcome"]
)
CHAT_DURATION = Histogram(
    "vyom_chat_duration_seconds",
    "Time from question to result, whatever the outcome.",
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120),
)
GRAPH_STEP_DURATION = Histogram(
    "vyom_graph_step_duration_seconds",
    "Duration of one step of the chat graph.",
    ["step"],
    buckets=(0.05, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60),
)

_chat_log = logging.getLogger("vyom.chat")


def record_chat(outcome: str, duration: float) -> None:
    """Count, time and log one chat question. ``outcome`` is one of the graph's fixed outcomes.

    The question, the answer and the evidence are never passed here.
    """
    CHAT_REQUESTS.labels(outcome).inc()
    CHAT_DURATION.observe(duration)
    _chat_log.log(
        logging.INFO if outcome == "answered" else logging.WARNING,
        "chat finished",
        extra={"operation": "chat", "outcome": outcome, "duration_ms": round(duration * 1000, 1)},
    )


def record_graph_step(step: str, duration: float) -> None:
    """``step`` is one of the graph's node names."""
    GRAPH_STEP_DURATION.labels(step).observe(duration)


COLLECTOR_RUNS = Counter(
    "vyom_collector_runs_total", "Direct collector runs.", ["collector", "outcome"]
)
COLLECTOR_DURATION = Histogram(
    "vyom_collector_duration_seconds", "Direct collector run duration.", ["collector"]
)
COLLECTOR_LAST_SUCCESS = Gauge(
    "vyom_collector_last_success_timestamp_seconds",
    "Unix time of the collector's last complete run. Absent until one succeeds.",
    ["collector"],
)

_collector_log = logging.getLogger("vyom.collector")


def record_collector_run(
    collector: str, *, outcome: str, duration: float, error_type: str | None = None
) -> None:
    """Count, time and log one direct collection. ``collector`` is a fixed name and
    ``outcome`` is ``ok`` or an error kind. Collected resources are never passed here."""
    COLLECTOR_RUNS.labels(collector, outcome).inc()
    COLLECTOR_DURATION.labels(collector).observe(duration)
    if outcome == "ok":
        COLLECTOR_LAST_SUCCESS.labels(collector).set_to_current_time()
    fields: dict[str, object] = {
        "operation": "collector.run",
        "outcome": outcome,
        "duration_ms": round(duration * 1000, 1),
        "collector": collector,
    }
    if error_type is not None:
        fields["error_type"] = error_type
    _collector_log.log(
        logging.INFO if outcome == "ok" else logging.WARNING,
        "collector run finished",
        extra=fields,
    )


def _metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ---- Traces --------------------------------------------------------------------------

_URL_ATTRIBUTES = ("http.url", "url.full", "http.target")
_DROPPED_ATTRIBUTES = ("url.query",)
_DROPPED_PREFIXES = ("http.request.header.", "http.response.header.")


def _without_query(url: str) -> str:
    return urlunsplit(urlsplit(url)._replace(query="", fragment=""))


def _scrub_attributes(attributes) -> dict:
    kept = {}
    for key, value in (attributes or {}).items():
        if key in _DROPPED_ATTRIBUTES or key.startswith(_DROPPED_PREFIXES):
            continue
        kept[key] = _without_query(value) if key in _URL_ATTRIBUTES else value
    return kept


def _scrub_event(event: Event) -> Event:
    attributes = dict(event.attributes or {})
    if event.name == "exception":
        attributes = {k: v for k, v in attributes.items() if k == "exception.type"}
    return Event(event.name, attributes, event.timestamp)


class ScrubbingExporter(SpanExporter):
    """Removes URL queries, headers and exception text before spans leave the process."""

    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export([self._scrub(span) for span in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)

    @staticmethod
    def _scrub(span: ReadableSpan) -> ReadableSpan:
        return ReadableSpan(
            name=span.name,
            context=span.context,
            parent=span.parent,
            resource=span.resource,
            attributes=_scrub_attributes(span.attributes),
            events=[_scrub_event(event) for event in span.events],
            links=span.links,
            kind=span.kind,
            instrumentation_scope=span.instrumentation_scope,
            status=span.status,
            start_time=span.start_time,
            end_time=span.end_time,
        )


def _otlp_configured() -> bool:
    return bool(
        os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        or os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    )


def tracer_provider() -> TracerProvider:
    """The process-wide provider, created on first use. Samples every trace (S1 demo traffic)."""
    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        return current
    provider = TracerProvider(
        resource=Resource.create({"service.name": SERVICE_NAME, "service.version": __version__})
    )
    if _otlp_configured():
        # Endpoint comes from the standard OTEL_EXPORTER_OTLP_* variables.
        provider.add_span_processor(
            BatchSpanProcessor(
                ScrubbingExporter(OTLPSpanExporter(timeout=3)),
                max_queue_size=512,  # spans beyond this are dropped, not buffered
                max_export_batch_size=128,
                schedule_delay_millis=2000,
                export_timeout_millis=5000,
            )
        )
    trace.set_tracer_provider(provider)
    return provider


def tracer() -> trace.Tracer:
    return tracer_provider().get_tracer("vyom")


def instrument(app: FastAPI) -> None:
    """Attach request metrics and logs, the /metrics endpoint and request tracing to ``app``."""
    app.middleware("http")(_observe_request)
    app.add_api_route("/metrics", _metrics, include_in_schema=False)
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=tracer_provider(),
        excluded_urls=",".join(sorted(_UNOBSERVED_ROUTES)),
        exclude_spans=["receive", "send"],  # one server span per request
    )
