"""Reasoning adapter against scripted HTTP responses. Fixture evidence only: nothing here
proves that the configured provider or model supports tool calling; scripts/model-check.sh
does that against the real endpoint."""

# asyncio runs async code from ordinary test functions; json parses text; logging is the
# built-in log system.
import asyncio
import json
import logging

# Third-party: httpx (HTTP), pytest (tests), langchain/langsmith (the model library and its
# tracing), opentelemetry + prometheus (spans and metrics to inspect), pydantic (validation).
import httpx
import langsmith.utils
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tracers.langchain import LangChainTracer
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import REGISTRY, generate_latest
from pydantic import ValidationError

from vyom import telemetry
from vyom.agent.model import ModelClient, ModelConfig, ModelError, ModelErrorKind, Usage
from vyom.mcp_client.host import ToolDescriptor
from vyom.mcp_client.registry import OperatorConfig

# Fake values only. The test text contains "marker" strings so we can check they never
# leak into logs, metrics or errors.
KEY = "sk-test-0123456789abcdef"
PROMPT = "which pods are unhealthy? prompt-marker-51"
PROVIDER_TEXT = "provider-error-text-77 echoing prompt-marker-51"
# A sample tool the model may propose to call.
TOOL = ToolDescriptor(
    "kubernetes__pods_list_in_namespace",
    "List pods.",
    {"type": "object", "properties": {"labelSelector": {"type": "string"}}},
)
LABELS = {"provider": "testprovider", "model": "vendor/test-model"}


# A fixture is setup code pytest passes to tests that ask for it by parameter name.
# ``monkeypatch`` sets environment variables only for the duration of one test.
@pytest.fixture
def config(monkeypatch) -> ModelConfig:
    monkeypatch.setenv("VYOM_TEST_MODEL_KEY", KEY)
    return ModelConfig(
        provider="testprovider",
        base_url="https://models.test/api/v1/",
        model="vendor/test-model",
        credential_ref="env:VYOM_TEST_MODEL_KEY",
    )


@pytest.fixture
# ``yield`` splits a fixture: code before runs as setup, the value after ``yield`` is what
# the test receives, and code after it runs as cleanup. Here the test gets a function that
# returns everything emitted (spans and log lines) so far.
def observed():
    """Everything the adapter emits: spans as exported, and log lines as formatted."""
    exported = InMemorySpanExporter()
    processor = SimpleSpanProcessor(telemetry.ScrubbingExporter(exported))
    telemetry.tracer_provider().add_span_processor(processor)
    lines: list[str] = []
    handler = logging.Handler()
    handler.setFormatter(telemetry.JsonFormatter())
    # Replace the handler's emit with a tiny function that stores each formatted log line.
    handler.emit = lambda record: lines.append(handler.format(record))
    logger = logging.getLogger("vyom.model")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield lambda: "".join(s.to_json() for s in exported.get_finished_spans()) + "\n".join(lines)
    logger.removeHandler(handler)
    processor.shutdown()


# Build a fake provider reply in the chat-completions JSON shape. ``**message`` merges
# the given dict into the message.
def completion(message: dict, *, finish="stop", usage=None) -> dict:
    body = {"choices": [{"message": {"role": "assistant", **message}, "finish_reason": finish}]}
    if usage is not None:
        body["usage"] = usage
    return body


# A fake reply in which the model proposes a tool call. ``arguments`` is usually JSON text.
def proposing(arguments, *, name=TOOL.id) -> dict:
    call = {"id": "call_1", "type": "function", "function": {"name": name, "arguments": arguments}}
    return completion({"content": None, "tool_calls": [call]}, finish="tool_calls")


# Run one chat against fake responses; returns the reply and the requests sent.
def chat(config, respond, messages=None, tools=(TOOL,)):
    """Run one chat against ``respond``; returns the reply and the requests that were sent."""
    sent: list[httpx.Request] = []

    # The fake server: record the request, answer with ``respond`` (a dict becomes a 200 JSON
    # reply; anything else is used as the response).
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        answer = respond(request) if callable(respond) else respond
        if isinstance(answer, dict):
            return httpx.Response(200, json=answer)
        return answer

    # MockTransport routes requests to our handler instead of the internet.
    client = ModelClient(config, transport=httpx.MockTransport(handler))
    # Default to a single human message if none was given.
    messages = messages or [HumanMessage(PROMPT)]
    return asyncio.run(client.chat(messages, tools)), sent


# Run a chat that must fail and return the error. ``**kwargs`` forwards extra named
# parameters to ``chat``.
def failure(config, respond, **kwargs) -> ModelError:
    # Passes only if ModelError is raised inside; ``caught.value`` is the exception.
    with pytest.raises(ModelError) as caught:
        chat(config, respond, **kwargs)
    return caught.value


# Read a Prometheus counter's current value (0.0 if it has not been created yet).
def metric(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, {**LABELS, **labels}) or 0.0


# Out and back: a proposed tool call is understood, then the call and its result are
# sent back in the provider's format.
def test_tool_call_round_trip_is_normalized_both_ways(config):
    usage = {"prompt_tokens": 120, "completion_tokens": 18, "total_tokens": 138}
    # Counters are shared by the whole process, so compare the change, not the absolute value.
    before = metric("vyom_model_tokens_total", direction="input")

    # ``{**a, "k": v}`` copies dict ``a`` and adds a key.
    proposed, sent = chat(config, {**proposing('{"labelSelector": "app=web"}'), "usage": usage})

    call = {"name": TOOL.id, "args": {"labelSelector": "app=web"}, "id": "call_1"}
    assert proposed.message.tool_calls == [{**call, "type": "tool_call"}]
    assert proposed.message.content == ""
    assert proposed.finish == "tool_calls"
    assert proposed.usage == Usage(120, 18)
    assert metric("vyom_model_tokens_total", direction="input") == before + 120
    request = json.loads(sent[0].content)
    assert str(sent[0].url) == "https://models.test/api/v1/chat/completions"
    assert sent[0].headers["authorization"] == f"Bearer {KEY}"
    assert request["model"] == "vendor/test-model"
    assert request["tools"] == [
        {
            "type": "function",
            "function": {
                "name": TOOL.id,
                "description": "List pods.",
                "parameters": TOOL.parameters,
            },
        }
    ]

    # (history is the conversation so far: question, proposal, tool result)
    # Second leg: the call and its result go back in the provider's shape.
    history = [
        HumanMessage(PROMPT),
        proposed.message,
        ToolMessage('{"items": []}', tool_call_id="call_1"),
    ]
    answer, sent = chat(config, completion({"content": "No pods."}), messages=history)

    assert isinstance(answer.message, AIMessage)
    assert (answer.message.content, answer.message.tool_calls) == ("No pods.", [])
    assert answer.finish == "stop"
    assert json.loads(sent[0].content)["messages"][1:] == [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": TOOL.id, "arguments": '{"labelSelector": "app=web"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": '{"items": []}'},
    ]


@pytest.mark.parametrize("reported", [None, {}, {"prompt_tokens": 12}])
# No usage report must be recorded as unavailable (None), never as 0 tokens.
def test_absent_usage_is_unavailable_not_zero(config, reported):
    tokens = metric("vyom_model_tokens_total", direction="input")
    unavailable = metric("vyom_model_usage_unavailable_total")

    reply, _ = chat(config, completion({"content": "ok"}, usage=reported))

    assert reply.usage is None
    assert metric("vyom_model_tokens_total", direction="input") == tokens
    assert metric("vyom_model_usage_unavailable_total") == unavailable + 1


@pytest.mark.parametrize(
    "arguments",
    ['{"labelSelector": ', '["app=web"]', '"app=web"', 7, {"labelSelector": "app=web"}],
)
# Each parametrize case above is run as its own test. Arguments that are not a JSON object
# must be rejected.
def test_malformed_tool_arguments_are_rejected(config, arguments):
    assert failure(config, proposing(arguments)).kind is ModelErrorKind.MALFORMED_TOOL_CALL


@pytest.mark.parametrize("name", ["", None, 3])
# A proposed call needs a non-empty string name.
def test_tool_call_without_a_name_is_rejected(config, name):
    assert failure(config, proposing("{}", name=name)).kind is ModelErrorKind.MALFORMED_TOOL_CALL


@pytest.mark.parametrize("identifier", ["", None])
# A proposed call needs a non-empty ID.
def test_tool_call_without_an_id_is_rejected(config, identifier):
    reply = proposing("{}")
    reply["choices"][0]["message"]["tool_calls"][0]["id"] = identifier
    assert failure(config, reply).kind is ModelErrorKind.MALFORMED_TOOL_CALL


# Even if LangSmith tracing is switched on in the environment, no prompts may be exported.
def test_ambient_langsmith_settings_export_nothing(config, monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_not_a_real_key")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://langsmith.test")
    tracers: list[object] = []
    # Swap in a recorder for the tracer's constructor: if one is ever created, it lands here.
    monkeypatch.setattr(LangChainTracer, "__init__", lambda self, *a, **k: tracers.append(self))
    # LangSmith caches settings, so clear the cache before and after.
    langsmith.utils.get_env_var.cache_clear()  # LangSmith caches its settings per process
    try:
        chat(config, completion({"content": "ok"}))
    finally:
        langsmith.utils.get_env_var.cache_clear()

    # LangChain creates a tracer per run when tracing is on; none means nothing to export.
    assert not tracers


# Returns a function that raises ``error`` when called, to simulate network failures.
def _raise(error):
    def respond(request):
        raise error

    return respond


@pytest.mark.parametrize(
    ("respond", "kind"),
    [
        (httpx.Response(401, text=PROVIDER_TEXT), ModelErrorKind.AUTH),
        (httpx.Response(402, text=PROVIDER_TEXT), ModelErrorKind.QUOTA),
        (httpx.Response(429, text=PROVIDER_TEXT), ModelErrorKind.RATE_LIMITED),
        (httpx.Response(400, text=PROVIDER_TEXT), ModelErrorKind.REJECTED),
        (httpx.Response(404, text=PROVIDER_TEXT), ModelErrorKind.REJECTED),
        (httpx.Response(503, text=PROVIDER_TEXT), ModelErrorKind.UNAVAILABLE),
        (httpx.Response(200, text=PROVIDER_TEXT), ModelErrorKind.INVALID_RESPONSE),
        (httpx.Response(200, json=[PROVIDER_TEXT]), ModelErrorKind.INVALID_RESPONSE),
        ({"choices": []}, ModelErrorKind.INVALID_RESPONSE),
        ({"error": {"code": 429, "message": PROVIDER_TEXT}}, ModelErrorKind.RATE_LIMITED),
        ({"error": {"message": PROVIDER_TEXT}}, ModelErrorKind.UNAVAILABLE),
        (_raise(httpx.ConnectError(PROVIDER_TEXT)), ModelErrorKind.UNAVAILABLE),
        (_raise(httpx.ReadTimeout(PROVIDER_TEXT)), ModelErrorKind.TIMEOUT),
    ],
)
# Every provider failure maps to one fixed kind, and the provider's text/keys/prompt never
# appear in errors, logs, spans or metrics.
def test_provider_failures_are_explicit_and_sanitized(config, observed, respond, kind):
    before = metric("vyom_model_requests_total", outcome=kind.value)

    error = failure(config, respond)

    assert error.kind is kind
    assert metric("vyom_model_requests_total", outcome=kind.value) == before + 1
    emitted = str(error) + repr(error) + observed() + generate_latest().decode()
    assert f'"outcome": "{kind.value}"' in emitted
    for secret in (KEY, "prompt-marker-51", "provider-error-text-77", "models.test"):
        assert secret not in emitted


# A reply bigger than max_response_bytes is discarded.
def test_reply_over_the_size_limit_is_discarded(config):
    small = config.model_copy(update={"max_response_bytes": 512})
    error = failure(small, completion({"content": "x" * 2048}))
    assert error.kind is ModelErrorKind.OVERSIZED


# With no readable key no request is sent. The lambda records the request, then ``or {}``
# returns an empty dict (``list.append`` returns None).
def test_missing_key_fails_before_any_request(config, observed, monkeypatch, tmp_path):
    monkeypatch.delenv("VYOM_TEST_MODEL_KEY")
    sent: list = []
    for ref in ("env:VYOM_TEST_MODEL_KEY", f"file:{tmp_path}/no-such-key"):
        missing = config.model_copy(update={"credential_ref": ref})

        error = failure(missing, lambda request: sent.append(request) or {})

        assert error.kind is ModelErrorKind.MISSING_CREDENTIAL
        assert "no-such-key" not in str(error) + observed()
    assert not sent


# Successful calls log identities and counts only, never content.
def test_success_telemetry_has_identities_and_counts_but_no_content(config, observed):
    usage = {"prompt_tokens": 9, "completion_tokens": 4}
    chat(config, completion({"content": "answer-marker-93"}, usage=usage))

    emitted = observed()
    assert '"model.client.chat"' in emitted
    assert '"vyom.model.provider": "testprovider"' in emitted
    assert '"input_tokens": 9' in emitted and '"output_tokens": 4' in emitted
    for secret in (KEY, "prompt-marker-51", "answer-marker-93", "models.test"):
        assert secret not in emitted + generate_latest().decode()


@pytest.mark.parametrize(
    "change",
    [
        {"base_url": "http://models.test/v1"},
        {"base_url": f"https://user:{KEY}@models.test/v1"},
        {"base_url": f"https://models.test/v1?key={KEY}"},
        {"credential_ref": KEY},
        {"provider": "Not A Label"},
        {"api_key": KEY},
    ],
)
# Unsafe settings (http, embedded key, wrong shapes) are rejected without repeating the key.
def test_config_rejects_unsafe_endpoints_and_inline_keys_without_echoing(config, change):
    with pytest.raises(ValidationError) as caught:
        # ``**`` unpacks a dict into named arguments; the second dict overrides the first.
        ModelConfig(**{**config.model_dump(), **change})
    assert KEY not in str(caught.value)


# The model section is optional in the config: absent means None.
def test_operator_file_carries_the_model_section():
    context = {"workspace_id": "w", "connection_id": "c", "cluster_uid": "u", "namespace": "demo"}
    model = {
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "anthropic/claude-haiku-5.5",
        "credential_ref": "file:/run/secrets/model-api-key",
    }
    assert OperatorConfig.model_validate({"context": context}).model is None
    loaded = OperatorConfig.model_validate({"context": context, "model": model})
    assert loaded.model.base_url == "https://openrouter.ai/api/v1"
