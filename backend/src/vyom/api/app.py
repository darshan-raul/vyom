import os

from fastapi import FastAPI
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, Field

from vyom import __version__, telemetry
from vyom.agent.graph import MAX_QUESTION_CHARS, ChatAgent, ChatResult, not_configured
from vyom.agent.model import ModelClient
from vyom.context import FixedContextResolver
from vyom.mcp_client.host import McpHost
from vyom.mcp_client.kubernetes import SPECS
from vyom.mcp_client.registry import OperatorConfig, load_operator_config

CONFIG_ENV = "VYOM_CONFIG"  # path of the operator configuration file


class Health(BaseModel):
    status: str
    service: str
    version: str


class ChatRequest(BaseModel):
    # The question is the only thing a browser may send: no scope, tool or endpoint field.
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


class ChatResponse(ChatResult):
    trace_id: str | None = None  # for finding this request's logs and trace; absent untraced


class Scope(BaseModel):
    connection_id: str
    namespace: str


class ModelInfo(BaseModel):
    provider: str
    model: str


class ToolInfo(BaseModel):
    id: str
    description: str


class AgentStatus(BaseModel):
    """What is configured, from operator configuration. It does not probe the model or MCP."""

    configured: bool
    scope: Scope | None = None
    model: ModelInfo | None = None
    tools: list[ToolInfo] = []
    max_question_chars: int = MAX_QUESTION_CHARS


def create_app(
    operator: OperatorConfig | None = None,
    *,
    host: McpHost | None = None,
    model: ModelClient | None = None,
) -> FastAPI:
    """Build the API. Without ``operator`` there is no agent and chat reports that.

    ``host`` and ``model`` replace the ones built from ``operator`` (tests only).
    """
    app = FastAPI(title="Vyom API", version=__version__)
    telemetry.instrument(app)

    resolver = FixedContextResolver(operator.context) if operator else None
    host = host or (McpHost(operator, SPECS) if operator else None)
    tools = host.tools() if host else []
    agent = (
        ChatAgent(model or ModelClient(operator.model), host)
        if operator and operator.model and host and tools
        else None
    )

    @app.get("/api/health")
    def health() -> Health:
        """Process liveness only; it does not check Kubernetes, MCP or the model provider."""
        return Health(status="ok", service=telemetry.SERVICE_NAME, version=__version__)

    @app.get("/api/agent")
    def agent_status() -> AgentStatus:
        if operator is None:
            return AgentStatus(configured=False)
        return AgentStatus(
            configured=agent is not None,
            scope=Scope(
                connection_id=operator.context.connection_id, namespace=operator.context.namespace
            ),
            model=operator.model
            and ModelInfo(provider=operator.model.provider, model=operator.model.model),
            tools=[ToolInfo(id=tool.id, description=tool.description) for tool in tools],
        )

    @app.post("/api/chat")
    async def chat(request: ChatRequest) -> ChatResponse:
        """One question, one bounded tool round, one answer. Every outcome is a 200 with an
        explicit ``outcome``; an unanswered question carries a ``limitation``, never a guess."""
        if agent is None or resolver is None:
            result = not_configured()
        else:
            # Authority comes from the server-side resolver, never from the request.
            result = await agent.ask(request.question, resolver.resolve())
        context = trace.get_current_span().get_span_context()
        return ChatResponse(
            **result.model_dump(),
            trace_id=format(context.trace_id, "032x") if context.is_valid else None,
        )

    return app


def _operator_from_environment() -> OperatorConfig | None:
    path = os.environ.get(CONFIG_ENV)
    return load_operator_config(path) if path else None


telemetry.configure_logging()
app = create_app(_operator_from_environment())
