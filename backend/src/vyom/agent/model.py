"""Reasoning adapter: one OpenAI-compatible chat endpoint through LangChain's ``ChatOpenAI``.

Callers pass LangChain messages and the MCP host's tool descriptors and get back a ``Reply``
holding the model's ``AIMessage``, or a ``ModelError`` with one of a fixed set of kinds. The
endpoint, model and key come from operator configuration; nothing in a request or a reply can
change them. The key is read from its reference for each request.

LangChain does the provider translation. This module adds what Vyom's rules need around it:
no retries, no LangSmith export, a reply size limit, fixed error kinds in place of provider
exception text, usage that stays unavailable when unreported, and payload-free telemetry.

A proposed tool call is untrusted. This module checks only that it is well formed (an ID, a
name and a JSON object of arguments); whether the tool is allowed and the arguments are valid
is the MCP host's decision.
"""

# Standard library: time measures how long a request takes.
import time

# Names used only in type hints: "a sequence of ..." and "an async stream of ...".
from collections.abc import AsyncIterator, Sequence

# @dataclass turns a plain class of named fields into a ready-made data holder.
from dataclasses import dataclass
from enum import StrEnum

# TYPE_CHECKING is False when the program runs and True only for type checkers. Imports
# under ``if TYPE_CHECKING:`` therefore cost nothing at runtime and avoid circular imports.
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit

# Third-party libraries: httpx (HTTP), openai (its error types), langchain (talks to the
# model provider), langsmith/opentelemetry (tracing), pydantic (validated config).
import httpx
import openai
from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI
from langsmith import tracing_context
from opentelemetry.trace import SpanKind, StatusCode
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from vyom import telemetry
from vyom.credentials import CredentialUnavailable, check_reference, read_credential

# A quoted type such as "ToolDescriptor" below names this class without importing it at
# runtime.
if TYPE_CHECKING:
    from vyom.mcp_client.host import ToolDescriptor


# Settings for the language model, read from the operator's config file. pydantic checks
# every field when the object is created.
class ModelConfig(BaseModel):
    # Validation errors must not echo a mistakenly pasted key.
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    # provider and model are metric labels: short, fixed by the operator.
    # Field(pattern=...) rejects values that do not match the regular expression;
    # gt/le are "greater than" / "less than or equal" limits on numbers.
    provider: str = Field(pattern=r"^[a-z][a-z0-9-]{0,30}$")
    base_url: str  # for example https://openrouter.ai/api/v1
    model: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
    credential_ref: str  # "file:/path" or "env:NAME"; the key never appears in configuration
    timeout_seconds: float = Field(default=30, gt=0, le=120)
    max_output_tokens: int = Field(default=1024, gt=0, le=8192)
    max_response_bytes: int = Field(default=262_144, gt=0, le=4_194_304)

    @field_validator("base_url")
    @classmethod
    # Only an https URL with no embedded password, query or fragment is accepted.
    # rstrip("/") removes a trailing slash so URLs are written one way.
    def _https_endpoint(cls, url: str) -> str:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            raise ValueError("base_url must be an https endpoint")
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("base_url must not carry credentials, a query or a fragment")
        return url.rstrip("/")

    @field_validator("credential_ref")
    @classmethod
    def _reference_only(cls, ref: str) -> str:
        return check_reference(ref)


# ---- Results -------------------------------------------------------------------------


# frozen=True: the object cannot be changed after it is created.
@dataclass(frozen=True)
# How many tokens (pieces of text) the request used. Tokens are what providers bill.
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
# A successful answer from the model.
class Reply:
    message: AIMessage  # text in ``content``, proposed calls in ``tool_calls``
    # "length": the reply was cut off at max_output_tokens.
    # Literal[...]: only these exact strings are allowed.
    finish: Literal["stop", "tool_calls", "length", "other"]
    usage: Usage | None  # None: the provider reported no usage. Unavailable, not zero.


# A fixed list of ways a model request can fail (an enum), used instead of free text.
class ModelErrorKind(StrEnum):
    MISSING_CREDENTIAL = "missing_credential"
    AUTH = "auth"
    QUOTA = "quota"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    REJECTED = "rejected"
    OVERSIZED = "oversized"
    INVALID_RESPONSE = "invalid_response"
    MALFORMED_TOOL_CALL = "malformed_tool_call"


# Safe, fixed text for each kind. The provider's own error text is never shown to users.
_MESSAGES = {
    ModelErrorKind.MISSING_CREDENTIAL: "The model credential is not configured or not readable.",
    ModelErrorKind.AUTH: "The model provider refused the configured credential.",
    ModelErrorKind.QUOTA: "The model provider account has no remaining quota.",
    ModelErrorKind.RATE_LIMITED: "The model provider is rate limiting requests.",
    ModelErrorKind.TIMEOUT: "The model provider did not answer in time.",
    ModelErrorKind.UNAVAILABLE: "The model provider could not be reached or failed.",
    ModelErrorKind.REJECTED: "The model provider rejected the request.",
    ModelErrorKind.OVERSIZED: "The model reply exceeded the configured size limit.",
    ModelErrorKind.INVALID_RESPONSE: "The model provider returned an unexpected response.",
    ModelErrorKind.MALFORMED_TOOL_CALL: "The model proposed a malformed tool call.",
}


# A custom exception. ``raise ModelError(kind)`` stops normal flow until some caller
# catches it with ``except ModelError``.
class ModelError(Exception):
    """A failed model request. Carries a kind and its fixed message, never provider text."""

    def __init__(self, kind: ModelErrorKind) -> None:
        # super() runs the parent class's __init__; here it sets the exception's message.
        super().__init__(_MESSAGES[kind])
        self.kind = kind


# ---- Translation ---------------------------------------------------------------------


# Convert one of Vyom's tool descriptions into the JSON shape the model API expects.
def _wire_tool(tool: "ToolDescriptor") -> dict[str, Any]:
    function = {"name": tool.id, "description": tool.description, "parameters": tool.parameters}
    return {"type": "function", "function": function}


# Map an HTTP status code (e.g. 429 = too many requests) to one of our error kinds.
def _kind_for_status(status: int) -> ModelErrorKind:
    if status in (401, 403):
        return ModelErrorKind.AUTH
    if status == 402:
        return ModelErrorKind.QUOTA
    if status == 429:
        return ModelErrorKind.RATE_LIMITED
    if status in (408, 504):
        return ModelErrorKind.TIMEOUT
    if status >= 500:
        return ModelErrorKind.UNAVAILABLE
    return ModelErrorKind.REJECTED


def _usage(message: AIMessage) -> Usage | None:
    # Read from the provider's own report: LangChain's usage_metadata fills gaps with zeros.
    # ``.get(key)`` returns None instead of failing when the key is missing.
    reported = message.response_metadata.get("token_usage")
    # isinstance(x, T) checks that x is of type T. If the provider sent no usable report,
    # return None ("unknown") rather than a made-up zero.
    if not isinstance(reported, dict):
        return None
    counts = (reported.get("prompt_tokens"), reported.get("completion_tokens"))
    # all(...) is True only if every item passes: both counts must be real ints, not negative.
    if not all(type(count) is int and count >= 0 for count in counts):
        return None
    # ``*counts`` unpacks the pair into two separate arguments.
    return Usage(*counts)


# Does every tool call the model proposed have a non-empty ID and name?
def _well_formed(message: AIMessage) -> bool:
    """LangChain sets aside arguments that are not JSON and refuses to build a message whose
    arguments are not an object (see ``_classify``); IDs and names are checked here."""
    if message.invalid_tool_calls:
        return False
    return all(
        isinstance(call["id"], str)
        and call["id"]
        and isinstance(call["name"], str)
        and call["name"]
        for call in message.tool_calls
    )


# Why did the model stop? A tool call, a normal stop, hitting the length limit, or other.
def _finish(message: AIMessage) -> Literal["stop", "tool_calls", "length", "other"]:
    if message.tool_calls:
        return "tool_calls"
    reason = message.response_metadata.get("finish_reason")
    return reason if reason in ("stop", "length") else "other"


# Turn whatever exception occurred into one of our fixed error kinds.
def _classify(error: Exception, oversized: bool) -> ModelErrorKind:
    """Map whatever LangChain or the OpenAI client raised to a kind. Its text is never used."""
    if oversized:
        return ModelErrorKind.OVERSIZED
    # Checks run from most specific to most general; the first match returns.
    if isinstance(error, openai.APITimeoutError):
        return ModelErrorKind.TIMEOUT
    if isinstance(error, openai.APIStatusError):
        return _kind_for_status(error.status_code)
    if isinstance(error, openai.APIConnectionError):
        return ModelErrorKind.UNAVAILABLE
    if isinstance(error, ValidationError):
        # LangChain could not build the message. Only the failing field names are read.
        # A set comprehension: the names of the fields that failed validation.
        fields = {issue["loc"][0] for issue in error.errors(include_input=False) if issue["loc"]}
        # ``<=`` on sets means "is a subset of".
        if fields and fields <= {"tool_calls", "invalid_tool_calls"}:
            return ModelErrorKind.MALFORMED_TOOL_CALL
    # Some gateways report an upstream failure inside a 200 response; LangChain raises it
    # as ValueError(<the error object>). Only an integer status code is read from it.
    # ``error.args`` holds what the exception was created with. This reads it only when it is
    # a ValueError carrying a dict.
    detail = error.args[0] if isinstance(error, ValueError) and error.args else None
    if isinstance(detail, dict):
        code = detail.get("code")
        return _kind_for_status(code) if type(code) is int else ModelErrorKind.UNAVAILABLE
    return ModelErrorKind.INVALID_RESPONSE


# ---- HTTP guard ----------------------------------------------------------------------


# The next two classes cap how large a response body may grow. Wrapping the network
# layer means the limit applies no matter what code reads the response.
class _CappedStream(httpx.AsyncByteStream):
    def __init__(self, inner: Any, guard: "_CappedTransport") -> None:
        self._inner, self._guard = inner, guard

    # ``async for`` over this object yields the body in chunks. ``yield`` hands out one chunk
    # at a time instead of building the whole list.
    async def __aiter__(self) -> AsyncIterator[bytes]:
        seen = 0
        async for chunk in self._inner:
            # Count bytes so far; stop if the total passes the limit.
            seen += len(chunk)
            if seen > self._guard.limit:
                self._guard.oversized = True
                raise httpx.StreamError("response exceeds the configured size limit")
            yield chunk

    async def aclose(self) -> None:
        await self._inner.aclose()


# A "transport" is the layer that actually sends the request. This one wraps a real
# transport and swaps the response body for the size-capped stream above.
class _CappedTransport(httpx.AsyncBaseTransport):
    """Stops reading a response body at the size limit."""

    def __init__(self, inner: httpx.AsyncBaseTransport, limit: int) -> None:
        self._inner, self.limit, self.oversized = inner, limit, False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            stream=_CappedStream(response.stream, self),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()


# ---- Client --------------------------------------------------------------------------


# The one entry point for talking to the model.
class ModelClient:
    # ``transport`` is an optional replacement network layer so tests can run without internet.
    # The bare ``*`` forces it to be passed by name.
    def __init__(
        self, config: ModelConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._config = config
        self._transport = transport  # tests only; None uses the network

    # ``async def`` marks a coroutine: a function that can pause at ``await`` while waiting
    # on the network, letting other work run. It must itself be awaited by the caller.
    async def chat(
        self, messages: Sequence[BaseMessage], tools: Sequence["ToolDescriptor"] = ()
    ) -> Reply:
        """One request, no retries. Raises ModelError; no other exception leaves this call."""
        config = self._config
        # A stopwatch: record the start time to compute the duration later.
        started = time.perf_counter()
        usage: Usage | None = None
        error_type = None
        outcome = "ok"
        # A ``with`` block sets something up and always cleans it up on exit. Here it opens a
        # trace "span", a timed record of this step that shows up in the tracing tool.
        with telemetry.tracer().start_as_current_span(
            "model.client.chat",
            kind=SpanKind.CLIENT,
            attributes={"vyom.model.provider": config.provider, "vyom.model.name": config.model},
        ) as span:
            try:
                message = await self._invoke(messages, tools)
                # Counted even if the reply is then rejected.
                usage = _usage(message)  # counted even if the reply is then rejected
                if not _well_formed(message):
                    raise ModelError(ModelErrorKind.MALFORMED_TOOL_CALL)
                span.set_attribute("vyom.model.tool_calls", len(message.tool_calls))
                return Reply(message, _finish(message), usage)
            # Catch our own error just to record details, then ``raise`` it again unchanged.
            except ModelError as error:
                outcome = error.kind.value
                # The class that caused it, when there was one; never its text.
                error_type = type(error.__context__ or error).__name__
                raise
            # ``finally`` always runs, whether the call returned, failed, or raised. It records the
            # metrics so every request is measured exactly once.
            finally:
                span.set_attribute("vyom.outcome", outcome)
                if usage is not None:
                    span.set_attribute("vyom.model.input_tokens", usage.input_tokens)
                    span.set_attribute("vyom.model.output_tokens", usage.output_tokens)
                if outcome != "ok":
                    span.set_status(StatusCode.ERROR)
                telemetry.record_model_request(
                    provider=config.provider,
                    model=config.model,
                    outcome=outcome,
                    duration=time.perf_counter() - started,
                    usage=(usage.input_tokens, usage.output_tokens) if usage else None,
                    error_type=error_type,
                )

    # Do the actual request. Everything that can go wrong is turned into a ModelError.
    async def _invoke(
        self, messages: Sequence[BaseMessage], tools: Sequence["ToolDescriptor"]
    ) -> AIMessage:
        config = self._config
        try:
            key = read_credential(config.credential_ref)
        except CredentialUnavailable:
            raise ModelError(ModelErrorKind.MISSING_CREDENTIAL) from None
        # ``a or b`` picks ``a`` if given, otherwise ``b`` (the real network transport).
        guard = _CappedTransport(
            self._transport or httpx.AsyncHTTPTransport(), config.max_response_bytes
        )
        try:
            # trust_env=False: no proxy or CA settings from the environment.
            async with httpx.AsyncClient(transport=guard, trust_env=False) as http:
                model = ChatOpenAI(
                    model=config.model,
                    base_url=config.base_url,
                    api_key=key,
                    http_async_client=http,
                    timeout=httpx.Timeout(config.timeout_seconds, connect=5),
                    max_retries=0,
                    max_tokens=config.max_output_tokens,
                )
                # Attach the tool definitions only if there are any (one-line if/else expression).
                runnable = (
                    model.bind_tools([_wire_tool(tool) for tool in tools]) if tools else model
                )
                # Never export messages through ambient LangSmith settings.
                with tracing_context(enabled=False):
                    message = await runnable.ainvoke(list(messages))
        # Catch anything at all so no provider error text escapes; replaced by a fixed kind.
        # ``from None`` hides the original exception chain.
        except Exception as error:
            raise ModelError(_classify(error, guard.oversized)) from None
        if not isinstance(message, AIMessage):
            raise ModelError(ModelErrorKind.INVALID_RESPONSE)
        return message
