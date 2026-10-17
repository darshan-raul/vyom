"""Direct read of pods from the Kubernetes API, for the deterministic resource view.

Independent of MCP: its own endpoint configuration, its own credential (a ServiceAccount
other than the MCP server's) and no shared code path with the MCP host beyond the evidence
contract. It asks the API server for its Table rendering with object metadata only, so pod
specs (and the literal environment values in them) are never sent to Vyom; readiness, status
and restarts are the same values `kubectl get pods` prints.
"""

# ssl = TLS/https certificates; time = durations; typing.Any = "any type";
# urlsplit splits a URL into its parts.
import ssl
import time
from typing import Any
from urllib.parse import urlsplit

# Third-party: httpx (HTTP client), opentelemetry (tracing), pydantic (validated settings).
import httpx
from opentelemetry.trace import SpanKind, StatusCode
from pydantic import BaseModel, ConfigDict, Field, field_validator

from vyom import telemetry
from vyom.context import TrustedContext
from vyom.credentials import CredentialUnavailable, check_reference, read_credential
from vyom.evidence import ErrorKind, Evidence, ItemDraft, build_evidence

# UPPER_CASE names are constants by convention. The Accept header below asks the
# Kubernetes API for a compact table instead of full pod objects.
COLLECTOR = "kubernetes-pods"  # source identity in evidence, and the telemetry label
_TABLE = "application/json;as=Table;g=meta.k8s.io;v=v1"
_COLUMNS = ("Name", "Ready", "Status", "Restarts")
# Read pods in pages of 100, at most 20 pages, so a huge cluster can't run away.
_PAGE_SIZE = 100
_MAX_PAGES = 20


# Where the Kubernetes API is and how to authenticate, from the operator's config file.
class KubernetesApiConfig(BaseModel):
    # Validation errors must not echo a mistakenly pasted credential.
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    connection_id: str  # the authorized connection this API server belongs to
    url: str  # for example https://kubernetes.default.svc
    ca_file: str | None = None
    # The collector's own ServiceAccount token: "file:/path" or "env:NAME".
    credential_ref: str
    timeout_seconds: float = Field(default=10, gt=0, le=60)
    max_response_bytes: int = Field(default=1_048_576, gt=0, le=8_388_608)  # per page
    # Field(default, gt=, le=) sets a default and allowed range (greater-than, less-or-equal).
    max_items: int = Field(default=500, gt=0, le=2000)

    @field_validator("url")
    @classmethod
    # Validator: runs when the config is loaded. Accept only the bare https server address;
    # returning the value accepts it, raising ValueError rejects it.
    def _https_endpoint(cls, url: str) -> str:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            raise ValueError("url must be an https endpoint")
        if (
            parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or parts.path.strip("/")
        ):
            raise ValueError("url must be the API server root, without credentials or a path")
        return url.rstrip("/")

    @field_validator("credential_ref")
    @classmethod
    def _reference_only(cls, ref: str) -> str:
        return check_reference(ref)


# Internal exception that carries one of our fixed error kinds.
class _Failure(Exception):
    def __init__(self, kind: ErrorKind) -> None:
        super().__init__(kind.value)
        self.kind = kind


# Map an HTTP status code (401 = not logged in, 403 = not allowed, ...) to an error kind.
def _kind_for_status(status: int) -> ErrorKind:
    if status == 401:
        return ErrorKind.AUTH
    if status == 403:
        return ErrorKind.FORBIDDEN
    if status in (408, 504):
        return ErrorKind.TIMEOUT
    if status >= 500:
        return ErrorKind.UNAVAILABLE
    return ErrorKind.UPSTREAM_ERROR


# Pick one error kind for any failure. Only the exception's type is used, never its
# text, which could contain private data.
def _classify(error: Exception) -> ErrorKind:
    """Map a failure to a kind. Exception text is never used."""
    if isinstance(error, _Failure):
        return error.kind
    if isinstance(error, CredentialUnavailable):
        return ErrorKind.AUTH
    # isinstance(x, A | B) means "x is an A or a B".
    if isinstance(error, TimeoutError | httpx.TimeoutException):
        return ErrorKind.TIMEOUT
    if isinstance(error, httpx.TransportError | OSError):
        return ErrorKind.UNAVAILABLE
    return ErrorKind.INVALID_OUTPUT


# Turn one page of the API's table into ItemDrafts. Any unexpected shape raises an
# error (KeyError etc.), which the caller reports as invalid output.
def _drafts(table: Any) -> list[ItemDraft]:
    """Project one Table page. Raises on any shape other than the expected one."""
    names = [column["name"] for column in table["columnDefinitions"]]
    # Find which column number holds each column we need.
    index = {name: names.index(name) for name in _COLUMNS}
    drafts = []
    for row in table["rows"]:
        # Tuple unpacking: two names assigned from two values on one line.
        cells, metadata = row["cells"], row["object"]["metadata"]
        drafts.append(
            ItemDraft(
                kind="Pod",
                namespace=metadata["namespace"],
                name=metadata["name"],
                uid=metadata["uid"],
                attributes={
                    "ready": str(cells[index["Ready"]]),
                    "status": str(cells[index["Status"]]),
                    # The API prints "4 (2m ago)" once a container has restarted.
                    "restarts": int(str(cells[index["Restarts"]]).split()[0]),
                },
            )
        )
    return drafts


# Reads pods straight from the Kubernetes API (no MCP, no model).
class PodCollector:
    # ``*`` makes ``transport`` keyword-only. It lets tests substitute a fake network.
    def __init__(
        self, config: KubernetesApiConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._config = config
        self._transport = transport  # tests only; None uses the network

    # ``async``: this can pause at each ``await`` while waiting on the network. Callers must
    # ``await`` it.
    async def collect(self, context: TrustedContext) -> Evidence:
        """List the pods in the context's namespace. Failures come back as evidence with an
        explicit error, never as an exception. ``context`` must come from the resolver."""
        # Stopwatch start, for the duration metric.
        started = time.perf_counter()
        drafts: list[ItemDraft] = []
        complete = True
        errors: list[ErrorKind] = []
        error_type = None
        # A ``with`` block that opens a trace span and closes it automatically at the end.
        with telemetry.tracer().start_as_current_span(
            "collector.kubernetes.pods",
            kind=SpanKind.CLIENT,
            attributes={"vyom.collector": COLLECTOR},
        ) as span:
            try:
                # The collector may only serve the connection it is configured for.
                if self._config.connection_id != context.connection_id:
                    raise _Failure(ErrorKind.SCOPE_VIOLATION)
                complete = await self._list(context.namespace, drafts)
            # Never let a failure escape as an exception: record it in the result instead.
            except Exception as error:
                # Pages read before a failure are kept; the evidence is then partial.
                errors.append(_classify(error))
                error_type = type(error).__name__
            with telemetry.tracer().start_as_current_span("evidence.normalize") as normalize:
                evidence = build_evidence(
                    context=context,
                    path="direct",
                    drafts=drafts,
                    complete=complete,
                    errors=errors,
                    collector=COLLECTOR,
                    max_items=self._config.max_items,
                )
                normalize.set_attribute("vyom.evidence.state", evidence.state.value)
                normalize.set_attribute("vyom.evidence.items", evidence.coverage.returned)
            # First error's name, or "ok" if the list is empty.
            outcome = errors[0].value if errors else "ok"
            span.set_attribute("vyom.outcome", outcome)
            span.set_attribute("vyom.evidence.state", evidence.state.value)
            if errors:
                span.set_status(StatusCode.ERROR)
        telemetry.record_collector_run(
            COLLECTOR,
            outcome=outcome,
            duration=time.perf_counter() - started,
            error_type=error_type,
        )
        return evidence

    # Fetch page after page, adding to ``drafts``. The True/False return says whether we
    # got everything.
    async def _list(self, namespace: str, drafts: list[ItemDraft]) -> bool:
        """Append every page to ``drafts``. Returns False if the list was cut short."""
        config = self._config
        # Read the token fresh for each run so a rotated token is picked up.
        token = read_credential(config.credential_ref)
        # ``verify`` is True (use the system's trusted certificates) or a custom SSL setup.
        verify: ssl.SSLContext | bool = True
        if config.ca_file:
            verify = ssl.create_default_context(cafile=config.ca_file)
        transport = self._transport or httpx.AsyncHTTPTransport(verify=verify)
        params: dict[str, str | int] = {"limit": _PAGE_SIZE, "includeObject": "Metadata"}
        # ``async with`` opens the HTTP client and always closes it, even after an error.
        # trust_env=False ignores proxy settings in environment variables.
        async with httpx.AsyncClient(
            transport=transport,
            base_url=config.url,
            headers={"Authorization": f"Bearer {token}", "Accept": _TABLE},
            timeout=httpx.Timeout(config.timeout_seconds, connect=5),
            trust_env=False,
        ) as http:
            # A loop with a hard upper bound. ``_`` means we don't use the loop counter.
            for _ in range(_MAX_PAGES):
                # Fetch one page.
                table = await self._page(http, f"/api/v1/namespaces/{namespace}/pods", params)
                try:
                    drafts.extend(_drafts(table))
                    token_next = table["metadata"].get("continue")
                except Exception:
                    # ``from None`` drops the original exception so its text can't leak.
                    raise _Failure(ErrorKind.INVALID_OUTPUT) from None
                if not token_next:
                    return True
                if len(drafts) > config.max_items:
                    return False  # build_evidence cuts at the limit and records the truncation
                # ``{**a, "k": v}`` copies dict ``a`` and adds/overrides a key.
                params = {**params, "continue": token_next}
        return False

    # Download one page, refusing anything not 200 OK or larger than the size limit.
    async def _page(self, http: httpx.AsyncClient, path: str, params: dict) -> Any:
        async with http.stream("GET", path, params=params) as response:
            if response.status_code != 200:
                raise _Failure(_kind_for_status(response.status_code))
            # A bytearray is a growable block of raw bytes; chunks are appended as they arrive.
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > self._config.max_response_bytes:
                    raise _Failure(ErrorKind.OVERSIZED)
        try:
            # Reuse httpx's JSON parsing on the collected bytes.
            return httpx.Response(200, content=bytes(body)).json()
        except ValueError:
            raise _Failure(ErrorKind.INVALID_OUTPUT) from None
