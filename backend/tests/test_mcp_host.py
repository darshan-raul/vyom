"""Host behavior against the offline fixture server. Fixture evidence only: nothing here
proves behavior of the upstream Kubernetes MCP server, which arrives in S1.3."""

# Standard library: asyncio (run async code), json, logging, socket (find a free network
# port), uuid (random IDs).
import asyncio
import json
import logging
import socket
import uuid

# replace(obj, field=value) returns a copy of a frozen dataclass with one field changed.
from dataclasses import replace

# pytest is the test framework. Shared fake-server helpers come from tests/mcp_fixture.py.
import pytest
from mcp_fixture import (
    CONTEXT,
    PODS,
    PODS_LIST,
    SECRET_ENV,
    TOKEN,
    TOOL,
    Upstream,
    config,
    run,
)

# Tools to capture spans and read metrics so tests can inspect what telemetry emitted.
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import generate_latest
from pydantic import ValidationError

from vyom import telemetry
from vyom.evidence import ErrorKind, ItemDraft, State, build_evidence
from vyom.mcp_client.host import McpHost
from vyom.mcp_client.registry import OperatorConfig


# Helper: call the tool through the host once. ``**kwargs`` forwards extra named options.
def call(upstream, operator_config, arguments=None, *, tool=TOOL, context=CONTEXT, **kwargs):
    return run(
        upstream, operator_config, lambda host: host.call(tool, arguments, context), **kwargs
    )


# Just the error kinds, to keep assertions short.
def kinds(evidence):
    return [error.kind for error in evidence.errors]


# Tests grouped by theme.
# ---- The working path ----------------------------------------------------------------


# Happy path: the right items, the namespace and credential come from the host, and
# nothing extra from the upstream leaks into the result.
def test_call_returns_projected_evidence_with_host_supplied_scope_and_credential(tmp_path):
    upstream = Upstream()

    evidence = call(upstream, config(tmp_path), {"label_selector": "app=web"})

    assert evidence.state is State.COMPLETE
    assert [(item.name, item.attributes) for item in evidence.items] == [
        ("web-1", {"phase": "Running", "restarts": 0}),
        ("job-7", {"phase": "Failed", "restarts": 4}),
    ]
    assert evidence.source.mcp.server_id == "kubernetes"
    assert evidence.source.mcp.tool_id == TOOL
    assert evidence.source.mcp.upstream_name == "fixture-kubernetes"
    # The namespace came from the trusted context, not from the proposed arguments.
    assert upstream.calls == [
        {"tool": "pods_list", "namespace": "demo", "label_selector": "app=web"}
    ]
    # The upstream returned literal env values; the projection did not keep them.
    assert SECRET_ENV not in evidence.model_dump_json()
    # A set comprehension: every request used exactly the host's own token.
    assert {headers["authorization"] for headers in upstream.headers} == {f"Bearer {TOKEN}"}


# Some upstreams refuse a non-localhost Host on a loopback connection (a sidecar proxy's).
# The option sends "localhost" and nothing else changes; without it the real Host is used.
def test_loopback_host_header_is_sent_only_when_configured(tmp_path):
    plain = Upstream()
    call(plain, config(tmp_path), None)
    assert all(headers["host"] != "localhost" for headers in plain.headers)

    guarded = Upstream()
    # The in-process fake applies its own Host rules, so only the header is asserted here;
    # the real upstream accepting it is checked live (scripts/vyom-check.sh).
    call(guarded, config(tmp_path, loopback_host_header=True), None)
    assert {headers["host"] for headers in guarded.headers} == {"localhost"}
    assert {headers["authorization"] for headers in guarded.headers} == {f"Bearer {TOKEN}"}


# The MCP path and the direct path must produce identical items, IDs and coverage.
def test_evidence_matches_the_direct_path_for_the_same_resources(tmp_path):
    drafts = [
        ItemDraft(
            kind="Pod",
            namespace=pod["namespace"],
            name=pod["name"],
            uid=pod["uid"],
            attributes={"phase": pod["phase"], "restarts": pod["restarts"]},
        )
        for pod in PODS
    ]
    direct = build_evidence(
        context=CONTEXT, path="direct", drafts=drafts, collector="kubernetes-sdk"
    )

    via_mcp = call(Upstream(), config(tmp_path))

    assert [item.id for item in via_mcp.items] == [item.id for item in direct.items]
    assert via_mcp.items == direct.items
    assert via_mcp.items[0].id == "k8s:c1uster-uid:demo:pod:web-1"
    assert via_mcp.coverage == direct.coverage
    assert via_mcp.state is direct.state
    # model_dump(include=...) keeps only the named fields, so we compare just the scope.
    scope = {"workspace_id", "connection_id", "cluster_uid", "namespace"}
    assert via_mcp.source.model_dump(include=scope) == direct.source.model_dump(include=scope)
    # Provenance differs by design and is recorded separately.
    assert (via_mcp.source.path, direct.source.path) == ("mcp", "direct")
    assert direct.source.mcp is None and via_mcp.source.collector is None
    # Both stamp host-clock UTC collection time; neither invents a source timestamp.
    assert abs(via_mcp.collected_at - direct.collected_at).total_seconds() < 5
    assert via_mcp.items[0].observed_at is None
    assert via_mcp.id != direct.id and via_mcp.id.startswith("ev_")


# A model or caller must not be able to choose scope, endpoint or credentials.
# ---- Caller- and model-controlled authority is refused -------------------------------


# Run the test below once per (input, expected) row.
@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"namespace": "kube-system"}, ErrorKind.SCOPE_VIOLATION),
        ({"cluster": "other-cluster"}, ErrorKind.INVALID_ARGUMENTS),
        ({"account": "111122223333"}, ErrorKind.INVALID_ARGUMENTS),
        ({"url": "http://attacker.example/mcp"}, ErrorKind.INVALID_ARGUMENTS),
        ({"authorization": "Bearer browser-token"}, ErrorKind.INVALID_ARGUMENTS),
        ({"kubeconfig": "/root/.kube/config"}, ErrorKind.INVALID_ARGUMENTS),
        ({"label_selector": {"$ne": ""}}, ErrorKind.INVALID_ARGUMENTS),
        ("namespace=kube-system", ErrorKind.INVALID_ARGUMENTS),
    ],
)
# Each hostile argument is refused and the upstream is never contacted.
def test_proposed_scope_endpoint_and_credential_arguments_never_reach_upstream(
    tmp_path, arguments, expected
):
    upstream = Upstream()

    evidence = call(upstream, config(tmp_path), arguments)

    assert kinds(evidence) == [expected]
    assert evidence.items == ()
    assert upstream.calls == [] and upstream.headers == []


# Passing the same namespace as the trusted one is harmless.
def test_repeating_the_trusted_namespace_is_accepted(tmp_path):
    assert call(Upstream(), config(tmp_path), {"namespace": "demo"}).state is State.COMPLETE


@pytest.mark.parametrize(
    "tool",
    [
        "kubernetes__pods_delete",  # advertised with readOnlyHint, never reviewed or enabled
        "kubernetes__pods_exec",
        "aws__pods_list",  # another server
        "http://attacker.example/mcp__pods_list",
        "pods_list",
        None,
    ],
)
# Unknown, unreviewed or invented tool names are refused before any network traffic.
def test_tools_outside_the_allowlist_are_refused_without_contacting_any_server(tmp_path, tool):
    upstream = Upstream()

    evidence = call(upstream, config(tmp_path), {"namespace": "demo", "name": "web-1"}, tool=tool)

    assert evidence.state is State.DENIED
    assert kinds(evidence) == [ErrorKind.TOOL_NOT_ALLOWED]
    assert evidence.source.mcp is None  # the proposed name is not echoed into evidence
    assert upstream.headers == []


# A reviewed tool still needs the operator to enable it.
def test_a_reviewed_tool_the_operator_did_not_enable_is_refused(tmp_path):
    upstream = Upstream()

    evidence = call(upstream, config(tmp_path, enabled_tools=[]))

    assert kinds(evidence) == [ErrorKind.TOOL_NOT_ALLOWED]
    assert upstream.headers == []


# A server tied to one connection can't be used from a context for another.
def test_an_endpoint_bound_to_another_connection_is_not_used(tmp_path):
    upstream = Upstream()
    other = CONTEXT.model_copy(update={"connection_id": "other-cluster"})

    evidence = call(upstream, config(tmp_path), context=other)

    assert evidence.state is State.DENIED
    assert kinds(evidence) == [ErrorKind.SCOPE_VIOLATION]
    assert upstream.headers == []


# Bad settings (literal secret, URLs with passwords, odd tool names, duplicates) fail.
def test_configuration_takes_credential_references_and_plain_endpoints_only(tmp_path):
    # A small helper inside the test.
    def load(**overrides):
        return config(tmp_path, **overrides)

    # Passes only if the code inside raises ValidationError; the error is kept in ``literal``.
    with pytest.raises(ValidationError) as literal:
        load(credential_ref="eyJhbGciOi.literal-token-value")
    assert "literal-token-value" not in str(literal.value)

    for bad in (
        {"url": "http://user:pass@mcp.vyom.svc/mcp"},
        {"url": "https://mcp.vyom.svc/mcp?token=abc"},
        {"url": "file:///etc/passwd"},
        {"allow_cleartext": False},  # the fixture url is http
        {"enabled_tools": ["pods list; rm -rf"]},
        {"headers": {"Authorization": "Bearer x"}},  # no such setting
    ):
        with pytest.raises(ValidationError):
            load(**bad)

    server = load().mcp_servers[0].model_dump()
    with pytest.raises(ValidationError):
        OperatorConfig.model_validate(
            {"context": CONTEXT.model_dump(), "mcp_servers": [server, server]}
        )


# Discovery lists what a server offers, but never enables anything by itself.
# ---- Annotations and discovery -------------------------------------------------------


# The server's own "read-only" claims and extra tools change nothing.
def test_discovery_enables_nothing_and_ignores_upstream_annotations(tmp_path):
    upstream = Upstream()

    # ``async def`` marks a coroutine, which can pause at ``await`` for network I/O. The
    # helper ``run`` executes it.
    async def work(host: McpHost):
        return await host.discover("kubernetes"), host.tools()

    discovery, tools = run(upstream, config(tmp_path), work)

    assert discovery.error is None
    assert discovery.tools == {TOOL: None}
    assert discovery.not_enabled == 1  # pods_delete: seen, counted, still not callable
    assert (discovery.upstream_name, discovery.upstream_version) == ("fixture-kubernetes", "0.0.1")
    assert discovery.protocol_version
    # The model sees Vyom's description and no scope argument.
    assert [(tool.id, tool.description) for tool in tools] == [(TOOL, PODS_LIST.description)]
    assert list(tools[0].parameters["properties"]) == ["label_selector"]


# Asking about a server not in the config is refused.
def test_an_unconfigured_server_cannot_be_discovered(tmp_path):
    discovery = run(Upstream(), config(tmp_path), lambda host: host.discover("http://x/mcp"))

    assert discovery.error is ErrorKind.TOOL_NOT_ALLOWED
    assert discovery.server_id == "unlisted"


# Every failure should give its own, explicit error kind.
# ---- Explicit failures ---------------------------------------------------------------


# If the server's tool schema differs from the reviewed one, the call is blocked.
def test_schema_drift_is_reported_by_discovery_and_blocks_the_call(tmp_path):
    upstream = Upstream(drifted=True)

    async def work(host: McpHost):
        return await host.discover("kubernetes"), await host.call(TOOL, None, CONTEXT)

    discovery, evidence = run(upstream, config(tmp_path), work)

    assert discovery.tools == {TOOL: ErrorKind.SCHEMA_MISMATCH}
    assert evidence.state is State.MISSING
    assert kinds(evidence) == [ErrorKind.SCHEMA_MISMATCH]
    assert upstream.calls == []


# A tool the server doesn't offer at all is also a schema mismatch.
def test_an_enabled_tool_the_server_does_not_advertise_is_a_mismatch(tmp_path):
    missing = replace(PODS_LIST, name="pods_top")

    evidence = call(
        Upstream(),
        config(tmp_path, enabled_tools=["pods_top"]),
        tool="kubernetes__pods_top",
        specs=(missing,),
    )

    assert kinds(evidence) == [ErrorKind.SCHEMA_MISMATCH]


# A 401/403 reply from the server becomes AUTH.
def test_a_rejected_credential_is_an_auth_error(tmp_path):
    upstream = Upstream()

    evidence = call(upstream, config(tmp_path, token="wrong-token"))

    assert evidence.state is State.DENIED
    assert kinds(evidence) == [ErrorKind.AUTH]
    assert upstream.calls == []


# If the secret can't be read, no request is sent.
def test_an_unreadable_credential_is_an_auth_error_without_a_request(tmp_path):
    upstream = Upstream()

    evidence = call(upstream, config(tmp_path, token=None))

    assert kinds(evidence) == [ErrorKind.AUTH]
    assert upstream.headers == []


# Too-large replies are dropped entirely, not cut into misleading evidence.
def test_oversized_output_is_discarded_not_truncated_into_evidence(tmp_path):
    big = {"pods": [{**PODS[0], "name": f"web-{n}", "note": "x" * 200} for n in range(400)]}
    limits = {"max_response_bytes": 8192}

    evidence = call(Upstream(payload=big), config(tmp_path, limits=limits))

    assert evidence.state is State.MISSING
    assert kinds(evidence) == [ErrorKind.OVERSIZED]
    assert evidence.items == ()


# Over the item limit the result is cut and marked PARTIAL.
def test_more_items_than_the_tool_limit_is_partial_and_says_so(tmp_path):
    many = {"pods": [{**PODS[0], "name": f"web-{n}"} for n in range(60)]}

    evidence = call(Upstream(payload=many), config(tmp_path))

    assert evidence.state is State.PARTIAL
    assert kinds(evidence) == [ErrorKind.TRUNCATED]
    assert (evidence.coverage.returned, evidence.coverage.truncated) == (50, True)


# A slow server hits the time limit and gives TIMEOUT.
def test_a_slow_tool_ends_at_the_time_limit(tmp_path):
    limits = {"connect_timeout_seconds": 0.5, "call_timeout_seconds": 0.5}

    evidence = call(Upstream(delay=5), config(tmp_path, limits=limits))

    assert evidence.state is State.MISSING
    assert kinds(evidence) == [ErrorKind.TIMEOUT]


# Output not in the expected shape is INVALID_OUTPUT.
def test_an_unexpected_result_shape_is_invalid_output(tmp_path):
    evidence = call(Upstream(payload={"items": "not pods"}), config(tmp_path))

    assert evidence.state is State.MISSING
    assert kinds(evidence) == [ErrorKind.INVALID_OUTPUT]


# Pods from a namespace we didn't ask for are not believed.
def test_results_from_another_namespace_are_refused(tmp_path):
    stray = {"pods": [{**PODS[0], "namespace": "kube-system"}]}

    evidence = call(Upstream(payload=stray), config(tmp_path))

    assert evidence.state is State.DENIED
    assert kinds(evidence) == [ErrorKind.SCOPE_VIOLATION]
    assert evidence.items == ()


# The upstream's error text never reaches the evidence.
def test_an_upstream_tool_error_is_reported_without_its_text(tmp_path):
    evidence = call(Upstream(fail=True), config(tmp_path))

    assert kinds(evidence) == [ErrorKind.UPSTREAM_ERROR]
    assert "fixture-upstream-detail" not in evidence.model_dump_json()


# A tool may translate a specific upstream error into FORBIDDEN.
def test_a_tool_can_map_an_upstream_denial_to_forbidden(tmp_path):
    spec = replace(PODS_LIST, error_kind=lambda text: ErrorKind.FORBIDDEN)

    evidence = call(Upstream(fail=True), config(tmp_path), specs=(spec,))

    assert evidence.state is State.DENIED
    assert kinds(evidence) == [ErrorKind.FORBIDDEN]
    assert "fixture-upstream-detail" not in evidence.model_dump_json()


# Uses a real unused port: the connection failure must come back as UNAVAILABLE.
def test_an_unreachable_endpoint_is_unavailable_not_an_exception_group(tmp_path):
    """Real sockets, no fixture: the SDK raises an ExceptionGroup that the host normalizes."""
    # Bind to port 0 so the OS picks a free port; then nothing is listening there.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    operator_config = config(tmp_path, url=f"http://127.0.0.1:{port}/mcp")
    host = McpHost(operator_config, (PODS_LIST,))

    evidence = asyncio.run(asyncio.wait_for(host.call(TOOL, None, CONTEXT), timeout=10))

    assert evidence.state is State.MISSING
    assert kinds(evidence) == [ErrorKind.UNAVAILABLE]


# Telemetry tests.
# ---- Telemetry -----------------------------------------------------------------------


# A log handler that stores each record as parsed JSON in a list.
class _Records(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []
        self.setFormatter(telemetry.JsonFormatter())

    # ``emit`` is called for each log record; we parse our formatter's JSON output.
    def emit(self, record):
        self.lines.append(json.loads(self.format(record)))


# Spans, metrics and logs use only configured IDs and never contain payloads; an invented
# tool name is recorded as "unlisted".
def test_spans_metrics_and_logs_carry_configured_ids_and_no_payload(tmp_path):
    exported = InMemorySpanExporter()
    telemetry.tracer_provider().add_span_processor(
        SimpleSpanProcessor(telemetry.ScrubbingExporter(exported))
    )
    records = _Records()
    logging.getLogger("vyom.mcp").addHandler(records)
    logging.getLogger("vyom.mcp").setLevel(logging.INFO)
    # A random tool name, to prove invented names never become labels.
    invented = f"kubernetes__{uuid.uuid4().hex}"
    selector = "app=selector-value-in-arguments"

    async def work(host: McpHost):
        with telemetry.tracer().start_as_current_span("test.request") as parent:
            await host.discover("kubernetes")
            await host.call(TOOL, {"label_selector": selector}, CONTEXT)
            await host.call(invented, {"label_selector": selector}, CONTEXT)
            return format(parent.get_span_context().trace_id, "032x")

    try:
        trace_id = run(Upstream(), config(tmp_path), work)
        run(Upstream(fail=True), config(tmp_path), lambda host: host.call(TOOL, None, CONTEXT))
    finally:
        logging.getLogger("vyom.mcp").removeHandler(records)

    spans = exported.get_finished_spans()
    by_name = {span.name: span for span in spans}
    assert {"mcp.client.discover", "mcp.client.call", "evidence.normalize"} <= set(by_name)
    # next(generator) returns the first span that matches.
    ok = next(s for s in spans if s.attributes.get("vyom.mcp.tool") == TOOL)
    assert ok.attributes["vyom.mcp.server"] == "kubernetes"
    assert ok.attributes["vyom.outcome"] == "ok"
    refused = next(s for s in spans if s.attributes.get("vyom.outcome") == "tool_not_allowed")
    assert refused.attributes["vyom.mcp.tool"] == "unlisted"
    assert not refused.status.is_ok

    exposition = generate_latest().decode()
    # Build the exact text of a Prometheus metric line with str.format placeholders ({}).
    labels = 'operation="call",outcome="{}",server="{}",tool="{}"'
    counter = "vyom_mcp_client_operations_total{{{}}}"
    assert counter.format(labels.format("ok", "kubernetes", TOOL)) in exposition
    assert counter.format(labels.format("tool_not_allowed", "unlisted", "unlisted")) in exposition
    assert counter.format(labels.format("upstream_error", "kubernetes", TOOL)) in exposition
    assert 'vyom_mcp_client_operation_duration_seconds_count{operation="discover"' in exposition

    assert [line["operation"] for line in records.lines] == [
        "mcp.discover",
        "mcp.call",
        "mcp.call",
        "mcp.call",
    ]
    assert records.lines[1]["mcp_tool"] == TOOL and records.lines[1]["outcome"] == "ok"
    assert records.lines[2]["mcp_tool"] == "unlisted"
    assert all(line["trace_id"] == trace_id for line in records.lines[:3])

    everything = exposition + json.dumps(records.lines) + "".join(s.to_json() for s in spans)
    # Nothing sensitive may appear anywhere in spans, metrics or logs.
    for forbidden in (
        invented,
        selector,
        TOKEN,
        SECRET_ENV,
        "fixture-upstream-detail",
        "web-1",
        "127.0.0.1",
    ):
        assert forbidden not in everything


# Log records from third-party libraries are dropped; Vyom's own are kept.
def test_client_library_log_records_are_dropped():
    # Helper: would a record from this logger name pass the filter?
    def passes(name):
        record = logging.LogRecord(
            name, logging.INFO, __file__, 1, "HTTP Request: POST ...", (), None
        )
        return telemetry._owned_or_safe(record)

    assert not passes("httpx2")
    assert not passes("mcp.client.streamable_http")
    assert passes("vyom.mcp")
    assert passes("mcpish")
