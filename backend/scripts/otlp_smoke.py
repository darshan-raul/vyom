"""Send one synthetic span through the backend's scrubbing OTLP exporter and print its trace ID.

Proves the OTLP pipeline only (backend exporter -> Alloy -> Tempo). It is not evidence of an
instrumented chat request. Exits non-zero if the collector does not accept the span. Run from
the repository root:

    OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 \
        uv run --project backend python backend/scripts/otlp_smoke.py
"""

# sys.exit("message") below stops the script with an error message and a non-zero code.
import sys

# Third-party: OpenTelemetry classes for creating spans and sending them out (OTLP).
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from vyom import telemetry

# Keep a copy of the finished span in memory so we can send it ourselves afterwards.
captured = InMemorySpanExporter()
# Get the app's tracing setup and attach the in-memory copy to it.
provider = telemetry.tracer_provider()
provider.add_span_processor(SimpleSpanProcessor(captured))
# Create one tiny span. ``with`` ends it automatically when the block finishes.
with provider.get_tracer("vyom.smoke").start_as_current_span("synthetic.smoke") as span:
    span.set_attribute("vyom.synthetic", True)
    # Write the trace ID as 32 hex digits, the form tracing tools display.
    trace_id = format(span.get_span_context().trace_id, "032x")

# Exported directly, not through the batch processor, so the result is known here.
# Send it through the same cleaning exporter the real app uses.
exporter = telemetry.ScrubbingExporter(OTLPSpanExporter(timeout=5))
# ``is not`` compares identity; anything other than SUCCESS means the collector refused it.
if exporter.export(captured.get_finished_spans()) is not SpanExportResult.SUCCESS:
    sys.exit("the collector did not accept the span; check OTEL_EXPORTER_OTLP_ENDPOINT")
# On success, print the ID so you can look the trace up.
print(trace_id)
