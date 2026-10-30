# os gives access to environment variables.
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

# FastAPI is the web framework; pydantic models describe the JSON the API returns.
import psycopg
from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, Field

from vyom import __version__, telemetry
from vyom.agent.graph import MAX_QUESTION_CHARS, ChatAgent, ChatResult, not_configured
from vyom.agent.model import ModelClient
from vyom.collectors.kubernetes import PodCollector
from vyom.context import FixedContextResolver
from vyom.credentials import CredentialUnavailable
from vyom.evidence import Evidence
from vyom.inventory import Database, DatabaseConfig, InventoryStore
from vyom.mcp_client.host import McpHost
from vyom.mcp_client.kubernetes import SPECS
from vyom.mcp_client.registry import OperatorConfig, load_operator_config

# Name of the environment variable that holds the config file path.
CONFIG_ENV = "VYOM_CONFIG"  # path of the operator configuration file
# Which identity mode the process runs in. Unset means production, so a deployment that
# forgets to choose fails closed instead of starting with the development identity.
MODE_ENV = "VYOM_MODE"
DEVELOPMENT = "development"
PRODUCTION = "production"


class DevelopmentIdentityRefused(Exception):
    """Production mode was asked to serve every request as the one configured operator."""


# Each BaseModel below is the shape of one JSON response (or request). FastAPI validates
# and documents it automatically.
class Health(BaseModel):
    status: str
    service: str
    version: str


# What the browser may send to /api/chat.
class ChatRequest(BaseModel):
    # The question is the only thing a browser may send: no scope, tool or endpoint field.
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    # min_length/max_length: reject an empty or oversized question.
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


# Everything in ChatResult (inherited) plus a trace ID.
class ChatResponse(ChatResult):
    trace_id: str | None = None  # for finding this request's logs and trace; absent untraced


# Which connection and namespace the agent is limited to.
class Scope(BaseModel):
    connection_id: str
    namespace: str


class ModelInfo(BaseModel):
    provider: str
    model: str


class ToolInfo(BaseModel):
    id: str
    description: str


# Used by GET /api/agent.
class AgentStatus(BaseModel):
    """What is configured, from operator configuration. It does not probe the model or MCP."""

    configured: bool
    scope: Scope | None = None
    model: ModelInfo | None = None
    # A default of ``[]`` is safe here: pydantic copies defaults per object.
    tools: list[ToolInfo] = []
    max_question_chars: int = MAX_QUESTION_CHARS


# Used by GET /api/kubernetes/pods.
class PodsView(BaseModel):
    """The direct collector's current read. ``evidence`` is absent only when no collector
    is configured; a failed read is evidence with an error, not an absent field."""

    configured: bool
    evidence: Evidence | None = None
    persisted: bool | None = None


# Used by GET /api/citations/{evidence_id}/{item_id}.
class CitationView(BaseModel):
    """The cited observation, resolved from stored collection runs and observations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    item_id: str
    collected_at: datetime
    run_state: str
    kind: str
    namespace: str | None = None
    name: str
    native_uid: str | None = None
    observed_at: datetime | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    resource_id: str | None = None
    resource_removed_at: datetime | None = None


# A factory function: builds the app from settings. Tests call it with fakes (host,
# model, pods) instead of real services. The bare ``*`` makes those keyword-only.
def create_app(
    operator: OperatorConfig | None = None,
    *,
    mode: str = DEVELOPMENT,
    host: McpHost | None = None,
    model: ModelClient | None = None,
    pods: PodCollector | None = None,
    database: DatabaseConfig | None = None,
    store: InventoryStore | None = None,
) -> FastAPI:
    """Build the API. Without ``operator`` there is no agent and chat reports that.

    ``mode`` is "development" or "production". Until S6 supplies a resolver that derives the
    context from a verified token, the only resolver is the fixed development one, so
    production mode refuses to build the app. ``host``, ``model``, ``pods``, ``database`` and
    ``store`` replace the ones built from ``operator`` (tests only).
    """
    if mode not in (DEVELOPMENT, PRODUCTION):
        raise ValueError(f"{MODE_ENV} must be '{DEVELOPMENT}' or '{PRODUCTION}'")
    if mode == PRODUCTION:
        raise DevelopmentIdentityRefused(
            "production mode needs an identity resolver that verifies the caller; "
            "only the fixed development identity exists until S6"
        )
    # The web application object. Routes are attached to it below.
    app = FastAPI(title="Vyom API", version=__version__)
    # Adds request logging, /metrics and tracing.
    telemetry.instrument(app)

    # ``X if condition else Y``: build only what the config provides, otherwise None.
    resolver = FixedContextResolver(operator.context) if operator else None

    # Persistent inventory store connection manager.
    db_config = database or (operator.database if operator else None)
    db = Database(db_config) if db_config else None

    @asynccontextmanager
    async def _resolve_store() -> AsyncIterator[InventoryStore]:
        if store is not None:
            yield store
        elif db is not None:
            async with db.store() as s:
                yield s
        else:
            raise RuntimeError("no store configured")

    # ``a or b`` uses ``a`` if it was passed in (tests), otherwise builds the real one.
    host = host or (McpHost(operator, SPECS) if operator else None)
    tools = host.tools() if host else []
    # The agent exists only if a model, a host and at least one tool are all configured.
    agent = (
        ChatAgent(
            model or ModelClient(operator.model),
            host,
            store=store,
            database=db,
        )
        if operator and operator.model and host and tools
        else None
    )

    pods = pods or (PodCollector(operator.kubernetes) if operator and operator.kubernetes else None)

    # A decorator: ``@app.get(path)`` registers the function below as the handler for GET
    # requests to that path. The return type tells FastAPI the response shape.
    @app.get("/api/health")
    def health() -> Health:
        """Process liveness only; it does not check Kubernetes, MCP or the model provider."""
        return Health(status="ok", service=telemetry.SERVICE_NAME, version=__version__)

    @app.get("/api/agent")
    # Reports what is configured; it does not call the model or MCP.
    def agent_status() -> AgentStatus:
        if operator is None:
            return AgentStatus(configured=False)
        return AgentStatus(
            configured=agent is not None,
            scope=Scope(
                connection_id=operator.context.connection_id, namespace=operator.context.namespace
            ),
            # ``x and Y`` is None when ``x`` is None, otherwise Y. Avoids a separate if.
            model=operator.model
            and ModelInfo(provider=operator.model.provider, model=operator.model.model),
            # A list comprehension: build a list by looping over ``tools`` in one expression.
            tools=[ToolInfo(id=tool.id, description=tool.description) for tool in tools],
        )

    # ``async def`` handlers can pause at ``await`` while waiting on the network.
    @app.get("/api/kubernetes/pods")
    async def kubernetes_pods() -> PodsView:
        """Pods in the configured namespace, read directly from the Kubernetes API with the
        collector's own identity. Independent of the agent, the model and MCP."""
        if pods is None or resolver is None:
            return PodsView(configured=False)
        context = resolver.resolve()
        evidence = await pods.collect(context)

        persisted: bool | None = None
        if store is not None or db is not None:
            started = time.perf_counter()
            try:
                async with _resolve_store() as inv_store:
                    await inv_store.record_collection(context, evidence, kind="Pod")
                persisted = True
                telemetry.record_inventory_operation(
                    "record_collection",
                    outcome="ok",
                    duration=time.perf_counter() - started,
                )
            except (psycopg.Error, CredentialUnavailable, OSError, TimeoutError) as error:
                persisted = False
                telemetry.record_inventory_operation(
                    "record_collection",
                    outcome="database_unavailable",
                    duration=time.perf_counter() - started,
                    error_type=type(error).__name__,
                )

        return PodsView(configured=True, evidence=evidence, persisted=persisted)

    @app.get("/api/citations/{evidence_id}/{item_id:path}")
    async def get_citation(evidence_id: str, item_id: str) -> CitationView:
        """Resolve one cited item from stored collection runs and observations."""
        if resolver is None:
            raise HTTPException(status_code=503, detail="service not configured")
        if store is None and db is None:
            raise HTTPException(status_code=503, detail="database not configured")

        context = resolver.resolve()
        started = time.perf_counter()
        try:
            async with _resolve_store() as inv_store:
                citation = await inv_store.resolve_citation(context, evidence_id, item_id)
        except (psycopg.Error, CredentialUnavailable, OSError, TimeoutError) as error:
            telemetry.record_inventory_operation(
                "resolve_citation",
                outcome="database_unavailable",
                duration=time.perf_counter() - started,
                error_type=type(error).__name__,
            )
            raise HTTPException(status_code=503, detail="database unavailable") from None

        telemetry.record_inventory_operation(
            "resolve_citation",
            outcome="ok" if citation is not None else "not_found",
            duration=time.perf_counter() - started,
        )

        if citation is None:
            raise HTTPException(status_code=404, detail="citation not found")

        return CitationView(
            run_id=citation.run_id,
            item_id=citation.item_id,
            collected_at=citation.collected_at,
            run_state=citation.run_state,
            kind=citation.kind,
            namespace=citation.namespace,
            name=citation.name,
            native_uid=citation.native_uid,
            observed_at=citation.observed_at,
            attributes=citation.attributes,
            resource_id=str(citation.resource_id) if citation.resource_id else None,
            resource_removed_at=citation.resource_removed_at,
        )

    # POST: the browser sends a JSON body, which FastAPI turns into a ChatRequest.
    @app.post("/api/chat")
    async def chat(request: ChatRequest) -> ChatResponse:
        """One question, one bounded tool round, one answer. Every outcome is a 200 with an
        explicit ``outcome``; an unanswered question carries a ``limitation``, never a guess."""
        if agent is None or resolver is None:
            result = not_configured()
        else:
            # Authority comes from the server-side resolver, never from the request.
            result = await agent.ask(request.question, resolver.resolve())
        # Get the current trace's ID so a user can find this request's logs and trace.
        context = trace.get_current_span().get_span_context()
        return ChatResponse(
            **result.model_dump(),
            trace_id=format(context.trace_id, "032x") if context.is_valid else None,
        )

    # Hand the finished app back to the caller.
    return app


# Read the config file path from the environment; no variable means no config.
def _operator_from_environment() -> OperatorConfig | None:
    path = os.environ.get(CONFIG_ENV)
    operator = load_operator_config(path) if path else None
    if operator and operator.database is None:
        db_ref = os.environ.get("VYOM_DATABASE_CREDENTIAL_REF")
        if not db_ref and os.environ.get("VYOM_DATABASE_URL"):
            db_ref = "env:VYOM_DATABASE_URL"
        if db_ref:
            operator = operator.model_copy(
                update={"database": DatabaseConfig(credential_ref=db_ref)}
            )
    return operator


# These two lines run when the module is imported. ``app`` is what the server (uvicorn)
# starts: ``uvicorn vyom.api.app:app``.
telemetry.configure_logging()
app = create_app(_operator_from_environment(), mode=os.environ.get(MODE_ENV) or PRODUCTION)
