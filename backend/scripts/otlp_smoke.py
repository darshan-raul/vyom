"""Send one synthetic span through the backend's scrubbing OTLP exporter and print its trace ID.

Proves the OTLP pipeline only (backend exporter -> Alloy -> Tempo). It is not evidence of an
instrumented chat request. Exits non-zero if the collector does not accept the span. Run from
the repository root:

    OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 \
        uv run --project backend python backend/scripts/otlp_smoke.py
"""

import sys

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from vyom import telemetry

captured = InMemorySpanExporter()
provider = telemetry.tracer_provider()
provider.add_span_processor(SimpleSpanProcessor(captured))
with provider.get_tracer("vyom.smoke").start_as_current_span("synthetic.smoke") as span:
    span.set_attribute("vyom.synthetic", True)
    trace_id = format(span.get_span_context().trace_id, "032x")

# Exported directly, not through the batch processor, so the result is known here.
exporter = telemetry.ScrubbingExporter(OTLPSpanExporter(timeout=5))
if exporter.export(captured.get_finished_spans()) is not SpanExportResult.SUCCESS:
    sys.exit("the collector did not accept the span; check OTEL_EXPORTER_OTLP_ENDPOINT")
print(trace_id)
