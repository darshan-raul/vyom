"""Live checks of the reasoning adapter against the configured OpenAI-compatible endpoint.

Run through scripts/model-check.sh, which locates the key and sets the environment below.
Sends a handful of small requests to the provider (a few thousand tokens in total). Prints
one PASS line per check and exits non-zero on a failure. The key is never printed.
"""

import asyncio
import json
import logging
import os
import sys

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import generate_latest

from vyom import telemetry
from vyom.agent.model import ModelClient, ModelConfig, ModelError, ModelErrorKind
from vyom.credentials import read_credential
from vyom.evidence import ErrorKind
from vyom.mcp_client.host import McpHost
from vyom.mcp_client.kubernetes import SPECS
from vyom.mcp_client.registry import OperatorConfig

CREDENTIAL_REF = os.environ["VYOM_MODEL_CREDENTIAL_REF"]  # file:/path or env:NAME
TOOL = "kubernetes__pods_list_in_namespace"
PROMPT_MARKER = "vyom-prompt-marker-7391"
BROKEN_POD = "broken-6d5f7c9b8-x2x4q"
SYSTEM = (
    "You answer questions about one Kubernetes namespace. Use the tool to read live state "
    "before answering, and name the pods you refer to."
)
# A canned result in the shape of Vyom evidence: this check is about the model exchange.
# The live MCP path was verified separately by scripts/mcp-check.sh.
TOOL_RESULT = json.dumps(
    {
        "state": "complete",
        "items": [
            {"name": "web-7c9d8f6b5-k4m2p", "ready": "1/1", "status": "Running", "restarts": 0},
            {"name": BROKEN_POD, "ready": "0/1", "status": "ImagePullBackOff", "restarts": 0},
        ],
    }
)

# The MCP endpoint is deliberately unreachable: only the host's own validation is used here.
OPERATOR = OperatorConfig.model_validate(
    {
        "context": {
            "workspace_id": "ws-local",
            "connection_id": "kind-vyom",
            "cluster_uid": "00000000-0000-0000-0000-000000000000",
            "namespace": "demo",
        },
        "mcp_servers": [
            {
                "id": "kubernetes",
                "connection_id": "kind-vyom",
                "url": "https://127.0.0.1:9/mcp",
                "credential_ref": "env:VYOM_UNUSED_MCP_TOKEN",
                "enabled_tools": ["pods_list_in_namespace"],
                "limits": {"connect_timeout_seconds": 2, "call_timeout_seconds": 2},
            }
        ],
        "model": {
            "provider": os.environ["VYOM_MODEL_PROVIDER"],
            "base_url": os.environ["VYOM_MODEL_BASE_URL"],
            "model": os.environ["VYOM_MODEL"],
            "credential_ref": CREDENTIAL_REF,
        },
    }
)
HOST = McpHost(OPERATOR, SPECS)


def passed(message: str) -> None:
    print(f"PASS  {message}")


def check(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL  {message}")
        sys.exit(1)
    passed(message)


def chat(messages, *, config: ModelConfig = OPERATOR.model, tools=None):
    tools = HOST.tools() if tools is None else tools
    return asyncio.run(ModelClient(config).chat(messages, tools))


def error_kind(config: ModelConfig) -> tuple[ModelErrorKind | None, str]:
    try:
        chat([HumanMessage(f"Say ok. {PROMPT_MARKER}")], config=config, tools=[])
    except ModelError as error:
        return error.kind, str(error) + repr(error)
    return None, ""


def host_verdict(arguments) -> list[ErrorKind]:
    evidence = asyncio.run(HOST.call(TOOL, arguments, OPERATOR.context))
    return [error.kind for error in evidence.errors]


def usage_text(reply) -> str:
    if reply.usage is None:
        return "usage not reported"
    return f"usage {reply.usage.input_tokens} in / {reply.usage.output_tokens} out"


def main() -> None:
    logging.getLogger().setLevel(logging.WARNING)
    os.environ["VYOM_UNUSED_MCP_TOKEN"] = "unused"
    exported = InMemorySpanExporter()
    telemetry.tracer_provider().add_span_processor(
        SimpleSpanProcessor(telemetry.ScrubbingExporter(exported))
    )
    records: list[str] = []
    handler = logging.Handler()
    handler.setFormatter(telemetry.JsonFormatter())
    handler.emit = lambda record: records.append(handler.format(record))
    for name in ("vyom.model", "vyom.mcp"):
        logging.getLogger(name).addHandler(handler)
        logging.getLogger(name).setLevel(logging.INFO)
    model = OPERATOR.model

    # Round trip, first leg: the model proposes the offered tool.
    question = HumanMessage(f"Which pods are unhealthy right now? ({PROMPT_MARKER})")
    history = [SystemMessage(SYSTEM), question]
    proposed = chat(history)
    calls = proposed.message.tool_calls
    check(
        proposed.finish == "tool_calls" and len(calls) == 1 and calls[0]["name"] == TOOL,
        f"{model.model} proposes one call of {TOOL} ({usage_text(proposed)})",
    )
    # The host accepts the proposed arguments: the only failure left is the dead endpoint.
    check(
        host_verdict(calls[0]["args"]) == [ErrorKind.UNAVAILABLE],
        f"the proposed arguments pass host validation (names: {sorted(calls[0]['args'])})",
    )

    # Second leg: the result goes back and the model answers from it.
    history += [proposed.message, ToolMessage(TOOL_RESULT, tool_call_id=calls[0]["id"])]
    answer = chat(history)
    check(
        answer.finish == "stop"
        and not answer.message.tool_calls
        and BROKEN_POD in answer.message.content,
        f"the answer after the tool result names the failing pod ({usage_text(answer)})",
    )

    # Arguments from the real model that the tool does not accept are refused by the host
    # before any request. "*" is outside the characters a label selector may contain.
    pushed = chat(
        [
            SystemMessage(SYSTEM),
            HumanMessage(
                "Which pods match the label selector app=web* ? Pass that selector to the "
                f"tool exactly as written. ({PROMPT_MARKER})"
            ),
        ]
    )
    calls = pushed.message.tool_calls
    check(
        len(calls) == 1
        and calls[0]["args"].get("labelSelector") == "app=web*"
        and host_verdict(calls[0]["args"]) == [ErrorKind.INVALID_ARGUMENTS],
        "a real proposed call with a selector outside the allowed pattern is refused: "
        "invalid_arguments" + ("" if calls else " (the model proposed no call)"),
    )

    # Arguments outside the offered schema. A model that follows the schema will not send
    # them, so these two are reported, not required; the offline tests and mcp-check.sh
    # cover the host's refusal either way.
    for instruction, argument, expected in (
        (
            "Call the tool with the extra argument fieldSelector set to status.phase=Failed.",
            "fieldSelector",
            ErrorKind.INVALID_ARGUMENTS,
        ),
        (
            "Call the tool with the argument namespace set to kube-system.",
            "namespace",
            ErrorKind.SCOPE_VIOLATION,
        ),
    ):
        pushed = chat(
            [
                SystemMessage("This is a test of argument validation. Do exactly as asked."),
                HumanMessage(f"{instruction} Do not explain. ({PROMPT_MARKER})"),
            ]
        )
        calls = pushed.message.tool_calls
        if len(calls) == 1 and argument in calls[0]["args"]:
            check(
                host_verdict(calls[0]["args"]) == [expected],
                f"a real proposed call with the unoffered argument {argument} is refused: "
                f"{expected.value}",
            )
        else:
            print(f"NOTE  not exercised live: the model would not send the argument {argument}")

    # Failures.
    os.environ["VYOM_BOGUS_MODEL_KEY"] = "sk-or-v1-" + "0" * 64
    cases = (
        ("a wrong key", {"credential_ref": "env:VYOM_BOGUS_MODEL_KEY"}, {ModelErrorKind.AUTH}),
        (
            "a missing key file",
            {"credential_ref": "file:/nonexistent/vyom-model-api-key"},
            {ModelErrorKind.MISSING_CREDENTIAL},
        ),
        (
            "an unset key variable",
            {"credential_ref": "env:VYOM_NO_SUCH_KEY"},
            {ModelErrorKind.MISSING_CREDENTIAL},
        ),
        (
            "a model the provider does not have",
            {"model": "vyom/no-such-model"},
            {ModelErrorKind.REJECTED},
        ),
        (
            "an unreachable provider",
            {"base_url": "https://127.0.0.1:9/v1"},
            {ModelErrorKind.UNAVAILABLE},
        ),
    )
    texts = ""
    for label, change, expected in cases:
        kind, text = error_kind(model.model_copy(update=change))
        texts += text
        check(kind in expected, f"{label} fails explicitly: {kind.value if kind else 'no error'}")

    # Nothing sensitive in what the adapter emitted.
    key = read_credential(CREDENTIAL_REF)
    spans = "".join(span.to_json() for span in exported.get_finished_spans())
    emitted = spans + "\n".join(records) + generate_latest().decode() + texts
    host = model.base_url.split("/")[2]
    leaks = {
        "the key": key,
        "the bogus key": os.environ["VYOM_BOGUS_MODEL_KEY"],
        "a prompt": PROMPT_MARKER,
        "a tool result": BROKEN_POD,
        "an answer": answer.message.content[:40],
        "the endpoint host": host,
    }
    found = [name for name, value in leaks.items() if value and value in emitted]
    check(
        not found,
        f"no key, prompt, tool result, answer or endpoint in {len(exported.get_finished_spans())} "
        f"spans, {len(records)} log lines, the metrics or the error texts"
        + (f": {found}" if found else ""),
    )
    outcomes = sorted({json.loads(line)["outcome"] for line in records})
    passed(f"logged outcomes: {outcomes}")


if __name__ == "__main__":
    try:
        main()
    except ModelError as error:
        print(f"FAIL  a request that should have succeeded failed: {error.kind.value}")
        sys.exit(1)
