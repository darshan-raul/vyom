"""The MCP host: connect, negotiate, discover and call under operator-configured policy.

Each operation opens its own short session and closes it: no session, credential or
discovered schema outlives the call it served. Callers supply a tool ID, proposed arguments
and the trusted context; they cannot supply an endpoint, a header or a credential.
Expected failures come back as evidence with an explicit error, never as an exception.
"""

import ssl
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import anyio
import httpx2
from mcp import Client
from mcp.shared.exceptions import MCPError
from mcp.types import REQUEST_TIMEOUT, TextContent, Tool
from opentelemetry.trace import Span, SpanKind, StatusCode
from pydantic import ValidationError

from vyom import telemetry
from vyom.context import TrustedContext
from vyom.evidence import ErrorKind, Evidence, ItemDraft, McpProvenance, build_evidence
from vyom.mcp_client import client_for
from vyom.mcp_client.registry import (
    CredentialUnavailable,
    OperatorConfig,
    ServerConfig,
    tool_id,
)
from vyom.mcp_client.tools import ToolOutput, ToolSpec, schema_digest

UNLISTED = "unlisted"  # telemetry label for any server or tool ID that is not configured
_MAX_TOOL_PAGES = 10

TransportFactory = Callable[[ServerConfig], httpx2.AsyncBaseTransport]


class _Failure(Exception):
    def __init__(self, kind: ErrorKind) -> None:
        super().__init__(kind.value)
        self.kind = kind


# ---- HTTP guard ----------------------------------------------------------------------


@dataclass
class _Wire:
    """What the HTTP layer saw during one session; the SDK does not surface either fact."""

    rejected: bool = False
    oversized: bool = False


class _CappedStream(httpx2.AsyncByteStream):
    def __init__(self, inner: Any, limit: int, wire: _Wire) -> None:
        self._inner, self._limit, self._wire = inner, limit, wire

    async def __aiter__(self) -> AsyncIterator[bytes]:
        seen = 0
        async for chunk in self._inner:
            seen += len(chunk)
            if seen > self._limit:
                self._wire.oversized = True
                raise httpx2.StreamError("response exceeds the configured size limit")
            yield chunk

    async def aclose(self) -> None:
        await self._inner.aclose()


class _GuardedTransport(httpx2.AsyncBaseTransport):
    """Stops reading a response body at the size limit and notes credential rejection."""

    def __init__(self, inner: httpx2.AsyncBaseTransport, limit: int, wire: _Wire) -> None:
        self._inner, self._limit, self._wire = inner, limit, wire

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        response = await self._inner.handle_async_request(request)
        if response.status_code in (401, 403):
            self._wire.rejected = True
        return httpx2.Response(
            response.status_code,
            headers=response.headers,
            stream=_CappedStream(response.stream, self._limit, self._wire),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()


def _network_transport(server: ServerConfig) -> httpx2.AsyncBaseTransport:
    verify: ssl.SSLContext | bool = True
    if server.ca_file:
        verify = ssl.create_default_context(cafile=server.ca_file)
    return httpx2.AsyncHTTPTransport(verify=verify)


def _leaves(error: BaseException) -> list[BaseException]:
    if isinstance(error, BaseExceptionGroup):
        return [leaf for inner in error.exceptions for leaf in _leaves(inner)]
    return [error]


def _classify(error: BaseException, wire: _Wire) -> tuple[ErrorKind, str]:
    """Map anything the SDK or transport raised, including its exception groups, to a kind.

    Returns the kind and the exception class name; exception text is never used.
    """
    leaves = _leaves(error)
    name = type(leaves[0]).__name__
    if wire.oversized:
        return ErrorKind.OVERSIZED, name
    if wire.rejected:
        return ErrorKind.AUTH, name
    for leaf in leaves:
        if isinstance(leaf, _Failure):
            return leaf.kind, type(leaf).__name__
        if isinstance(leaf, CredentialUnavailable):
            return ErrorKind.AUTH, type(leaf).__name__
    for leaf in leaves:
        timed_out = isinstance(leaf, TimeoutError | httpx2.TimeoutException) or (
            isinstance(leaf, MCPError) and leaf.code == REQUEST_TIMEOUT
        )
        if timed_out:
            return ErrorKind.TIMEOUT, type(leaf).__name__
    for leaf in leaves:
        if isinstance(leaf, httpx2.TransportError):
            return ErrorKind.UNAVAILABLE, type(leaf).__name__
    return ErrorKind.PROTOCOL, name


# ---- Results -------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolDescriptor:
    """What the model is shown: Vyom's own description and argument schema."""

    id: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class Discovery:
    server_id: str
    error: ErrorKind | None = None  # set when the server could not be discovered at all
    upstream_name: str | None = None
    upstream_version: str | None = None
    protocol_version: str | None = None
    # Enabled tool ID -> None when callable, or why it is not.
    tools: Mapping[str, ErrorKind | None] = field(default_factory=dict)
    # Advertised by the server but not enabled here. Reported, never enabled.
    not_enabled: int = 0


@dataclass
class _CallResult:
    drafts: tuple[ItemDraft, ...] = ()
    complete: bool = True
    upstream_name: str | None = None
    upstream_version: str | None = None
    protocol_version: str | None = None


# ---- Host ----------------------------------------------------------------------------


class McpHost:
    def __init__(
        self,
        config: OperatorConfig,
        specs: Sequence[ToolSpec] = (),
        *,
        transport_factory: TransportFactory = _network_transport,
    ) -> None:
        self._config = config
        self._transport_factory = transport_factory
        # Callable = reviewed here AND enabled by the operator. Discovery adds nothing.
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs:
            server = config.server(spec.server_id)
            if server is not None and spec.name in server.enabled_tools:
                self._specs[tool_id(spec.server_id, spec.name)] = spec

    def tools(self) -> list[ToolDescriptor]:
        """The enabled tools, described by Vyom. Scope arguments are not offered."""
        descriptors = []
        for identifier, spec in sorted(self._specs.items()):
            parameters = spec.arguments.model_json_schema()
            for name in spec.scope_arguments:
                parameters.get("properties", {}).pop(name, None)
            descriptors.append(ToolDescriptor(identifier, spec.description, parameters))
        return descriptors

    # -- discovery --

    async def discover(self, server_id: str) -> Discovery:
        server = self._config.server(server_id)
        label = server.id if server else UNLISTED
        started = time.perf_counter()
        error_type = None
        with self._span("mcp.client.discover", label, "") as span:
            if server is None:
                discovery = Discovery(UNLISTED, error=ErrorKind.TOOL_NOT_ALLOWED)
            else:
                wire = _Wire()
                try:
                    discovery = await self._session(server, wire, self._inspect(server))
                except Exception as error:
                    kind, error_type = _classify(error, wire)
                    discovery = Discovery(server.id, error=kind)
            problems = [discovery.error, *discovery.tools.values()]
            outcome = next((kind.value for kind in problems if kind), "ok")
            self._finish(span, outcome)
        telemetry.record_mcp_operation(
            "discover",
            server=label,
            tool="",
            outcome=outcome,
            duration=time.perf_counter() - started,
            error_type=error_type,
        )
        return discovery

    def _inspect(self, server: ServerConfig) -> Callable[[Client], Awaitable[Discovery]]:
        async def inspect(client: Client) -> Discovery:
            advertised = await _advertised(client)
            mine = {i: s for i, s in self._specs.items() if s.server_id == server.id}
            info = client.server_info
            return Discovery(
                server.id,
                upstream_name=info.name if info else None,
                upstream_version=(info.version or None) if info else None,
                protocol_version=client.protocol_version,
                tools={i: _mismatch(spec, advertised) for i, spec in mine.items()},
                not_enabled=len(advertised.keys() - {spec.name for spec in mine.values()}),
            )

        return inspect

    # -- call --

    async def call(
        self, tool: str, arguments: Mapping[str, Any] | None, context: TrustedContext
    ) -> Evidence:
        """Call one enabled tool within ``context`` and return normalized evidence.

        ``tool`` and ``arguments`` are untrusted (a model proposed them). ``context`` must
        come from the server-side resolver.
        """
        spec = self._specs.get(tool) if isinstance(tool, str) else None
        server_label = spec.server_id if spec else UNLISTED
        tool_label = tool if spec else UNLISTED
        started = time.perf_counter()
        error_type = None
        result = _CallResult()
        errors: list[ErrorKind] = []

        with self._span("mcp.client.call", server_label, tool_label) as span:
            wire = _Wire()
            try:
                if spec is None:
                    raise _Failure(ErrorKind.TOOL_NOT_ALLOWED)
                server = self._config.server(spec.server_id)
                if server is None or server.connection_id != context.connection_id:
                    raise _Failure(ErrorKind.SCOPE_VIOLATION)
                upstream_arguments = _bind_arguments(spec, arguments, context)
                result = await self._session(server, wire, _invoke(spec, upstream_arguments))
            except Exception as error:
                kind, error_type = _classify(error, wire)
                errors.append(kind)

            with telemetry.tracer().start_as_current_span("evidence.normalize") as normalize:
                evidence = build_evidence(
                    context=context,
                    path="mcp",
                    drafts=result.drafts,
                    complete=result.complete,
                    errors=errors,
                    mcp=spec
                    and McpProvenance(
                        server_id=spec.server_id,
                        tool_id=tool,
                        upstream_name=result.upstream_name,
                        upstream_version=result.upstream_version,
                        protocol_version=result.protocol_version,
                    ),
                    max_items=spec.max_items if spec else None,
                )
                normalize.set_attribute("vyom.evidence.state", evidence.state.value)
                normalize.set_attribute("vyom.evidence.items", evidence.coverage.returned)
            outcome = errors[0].value if errors else "ok"
            span.set_attribute("vyom.evidence.state", evidence.state.value)
            self._finish(span, outcome)

        telemetry.record_mcp_operation(
            "call",
            server=server_label,
            tool=tool_label,
            outcome=outcome,
            duration=time.perf_counter() - started,
            error_type=error_type,
        )
        return evidence

    # -- plumbing --

    async def _session[T](
        self, server: ServerConfig, wire: _Wire, work: Callable[[Client], Awaitable[T]]
    ) -> T:
        """Connect and negotiate, run ``work``, close. One deadline covers all of it."""
        limits = server.limits
        token = server.read_credential()
        transport = _GuardedTransport(
            self._transport_factory(server), limits.max_response_bytes, wire
        )
        with anyio.fail_after(limits.connect_timeout_seconds + limits.call_timeout_seconds):
            async with httpx2.AsyncClient(
                transport=transport,
                # The only credential ever sent: the host's own, from its reference.
                headers={"Authorization": f"Bearer {token}"},
                timeout=httpx2.Timeout(
                    limits.call_timeout_seconds, connect=limits.connect_timeout_seconds
                ),
                trust_env=False,
            ) as http:
                async with client_for(
                    server.url,
                    http_client=http,
                    read_timeout_seconds=limits.call_timeout_seconds,
                    max_sse_event_size=limits.max_response_bytes,
                ) as client:
                    if client.server_capabilities.tools is None:
                        raise _Failure(ErrorKind.PROTOCOL)
                    return await work(client)

    @staticmethod
    def _span(name: str, server: str, tool: str):
        attributes = {"vyom.mcp.server": server}
        if tool:
            attributes["vyom.mcp.tool"] = tool
        return telemetry.tracer().start_as_current_span(
            name, kind=SpanKind.CLIENT, attributes=attributes
        )

    @staticmethod
    def _finish(span: Span, outcome: str) -> None:
        span.set_attribute("vyom.outcome", outcome)
        if outcome != "ok":
            span.set_status(StatusCode.ERROR)


async def _advertised(client: Client) -> dict[str, Tool]:
    tools: dict[str, Tool] = {}
    cursor = None
    for _ in range(_MAX_TOOL_PAGES):
        page = await client.list_tools(cursor=cursor)
        tools.update({tool.name: tool for tool in page.tools})
        cursor = page.next_cursor
        if cursor is None:
            return tools
    raise _Failure(ErrorKind.PROTOCOL)


def _mismatch(spec: ToolSpec, advertised: Mapping[str, Tool]) -> ErrorKind | None:
    """Not advertised, or advertised with a schema other than the reviewed one."""
    upstream = advertised.get(spec.name)
    if upstream is None or schema_digest(upstream.input_schema) != spec.input_schema_sha256:
        return ErrorKind.SCHEMA_MISMATCH
    return None


def _bind_arguments(
    spec: ToolSpec, proposed: Mapping[str, Any] | None, context: TrustedContext
) -> dict[str, Any]:
    """Validate proposed arguments, then set scope arguments from the trusted context."""
    if proposed is not None and not isinstance(proposed, Mapping):
        raise _Failure(ErrorKind.INVALID_ARGUMENTS)
    remaining = dict(proposed or {})
    scope = {name: getattr(context, attr) for name, attr in spec.scope_arguments.items()}
    for name, trusted in scope.items():
        # Repeating the trusted value is harmless; asking for any other scope is refused.
        if name in remaining and remaining.pop(name) != trusted:
            raise _Failure(ErrorKind.SCOPE_VIOLATION)
    try:
        validated = spec.arguments.model_validate(remaining)
    except ValidationError:
        raise _Failure(ErrorKind.INVALID_ARGUMENTS) from None
    return {**validated.model_dump(exclude_none=True), **scope}


def _invoke(
    spec: ToolSpec, arguments: dict[str, Any]
) -> Callable[[Client], Awaitable[_CallResult]]:
    async def invoke(client: Client) -> _CallResult:
        # Checked on this session, immediately before the call it guards.
        if _mismatch(spec, await _advertised(client)) is not None:
            raise _Failure(ErrorKind.SCHEMA_MISMATCH)
        try:
            raw = await client.call_tool(spec.name, arguments)
        except RuntimeError:
            # The SDK's check of structured content against the advertised output schema.
            raise _Failure(ErrorKind.INVALID_OUTPUT) from None
        text = "\n".join(block.text for block in raw.content if isinstance(block, TextContent))
        if raw.is_error:
            raise _Failure(spec.error_kind(text) if spec.error_kind else ErrorKind.UPSTREAM_ERROR)
        try:
            projection = spec.project(ToolOutput(text=text, structured=raw.structured_content))
        except Exception:
            raise _Failure(ErrorKind.INVALID_OUTPUT) from None
        info = client.server_info
        return _CallResult(
            drafts=tuple(projection.items),
            complete=projection.complete,
            upstream_name=info.name if info else None,
            upstream_version=(info.version or None) if info else None,
            protocol_version=client.protocol_version,
        )

    return invoke
