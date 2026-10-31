"""Direct reads of namespaced workloads from the Kubernetes API, for the deterministic inventory.

Independent of MCP: its own endpoint configuration, its own credential (a ServiceAccount
other than the MCP server's) and no shared code path with the MCP host beyond the evidence
contract. It asks the API server for its Table rendering with object metadata only, so specs
(and the literal environment values in them) are never sent to Vyom; the projected columns are
the values `kubectl get` prints. Object metadata can still carry annotations, including
`kubectl.kubernetes.io/last-applied-configuration`: each projection below reads named fields
only and everything else is dropped unread, never stored or logged (decision KINV01).

One collector per kind (``Projection``). ``SWEEP`` lists them owners first, so a sweep stores
a Deployment before its ReplicaSets and a ReplicaSet before its Pods and the store can link
each owned object to its controller.
"""

# ssl = TLS/https certificates; time = durations; typing.Any = "any type";
# urlsplit splits a URL into its parts.
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

# Third-party: httpx (HTTP client), opentelemetry (tracing), pydantic (validated settings).
import httpx
from opentelemetry.trace import SpanKind, StatusCode
from pydantic import BaseModel, ConfigDict, Field, field_validator

from vyom import telemetry
from vyom.context import TrustedContext
from vyom.credentials import CredentialUnavailable, check_reference, read_credential
from vyom.evidence import ErrorKind, Evidence, ItemDraft, OwnerRef, Scalar, build_evidence

# UPPER_CASE names are constants by convention. The Accept header below asks the
# Kubernetes API for a compact table instead of full objects.
_TABLE = "application/json;as=Table;g=meta.k8s.io;v=v1"
# The only annotation read: the rollout revision the Deployment controller writes on a
# Deployment and on each of its ReplicaSets.
_REVISION = "deployment.kubernetes.io/revision"
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


# A cell such as "4 (2m ago)" (restarts) or "3" (replicas) as its leading integer.
def _count(cell: Any) -> int:
    return int(str(cell).split()[0])


def _revision(metadata: dict[str, Any]) -> int | None:
    value = (metadata.get("annotations") or {}).get(_REVISION)
    return int(value) if value is not None else None


@dataclass(frozen=True)
class Projection:
    """What one collector reads and keeps for one kind. Reviewed per kind: a column or
    metadata field not named here never reaches evidence."""

    kind: str
    collector: str  # source identity in evidence, and the telemetry label
    path: str  # the namespaced list path; ``{namespace}`` is filled from the trusted context
    columns: tuple[str, ...]  # Table columns the projection reads
    # (cells by column name, object metadata) -> attributes
    attributes: Callable[[dict[str, Any], dict[str, Any]], dict[str, Scalar]]


POD = Projection(
    kind="Pod",
    collector="kubernetes-pods",
    path="/api/v1/namespaces/{namespace}/pods",
    columns=("Name", "Ready", "Status", "Restarts"),
    attributes=lambda cells, _metadata: {
        "ready": str(cells["Ready"]),
        "status": str(cells["Status"]),
        # The API prints "4 (2m ago)" once a container has restarted.
        "restarts": _count(cells["Restarts"]),
    },
)
DEPLOYMENT = Projection(
    kind="Deployment",
    collector="kubernetes-deployments",
    path="/apis/apps/v1/namespaces/{namespace}/deployments",
    columns=("Name", "Ready", "Up-to-date", "Available"),
    attributes=lambda cells, metadata: {
        "ready": str(cells["Ready"]),
        "up_to_date": _count(cells["Up-to-date"]),
        "available": _count(cells["Available"]),
        "revision": _revision(metadata),
    },
)
REPLICA_SET = Projection(
    kind="ReplicaSet",
    collector="kubernetes-replicasets",
    path="/apis/apps/v1/namespaces/{namespace}/replicasets",
    columns=("Name", "Desired", "Current", "Ready"),
    attributes=lambda cells, metadata: {
        "desired": _count(cells["Desired"]),
        "current": _count(cells["Current"]),
        "ready": _count(cells["Ready"]),
        "revision": _revision(metadata),
    },
)
# Owners before owned objects; see the module docstring.
SWEEP = (DEPLOYMENT, REPLICA_SET, POD)
COLLECTOR = POD.collector  # kept for callers that predate the other kinds


# The controller among the owner references, if any. Other owners are not relationships Vyom
# tracks: ownership edges follow the controller only.
def _owner(metadata: dict[str, Any]) -> OwnerRef | None:
    for ref in metadata.get("ownerReferences") or ():
        if ref.get("controller"):
            return OwnerRef(kind=ref["kind"], name=ref["name"], uid=ref["uid"])
    return None


# Turn one page of the API's table into ItemDrafts. Any unexpected shape raises an
# error (KeyError etc.), which the caller reports as invalid output.
def _drafts(projection: Projection, table: Any) -> list[ItemDraft]:
    """Project one Table page. Raises on any shape other than the expected one."""
    names = [column["name"] for column in table["columnDefinitions"]]
    # Find which column number holds each column we need.
    index = {name: names.index(name) for name in projection.columns}
    drafts = []
    for row in table["rows"]:
        # Tuple unpacking: two names assigned from two values on one line.
        cells, metadata = row["cells"], row["object"]["metadata"]
        drafts.append(
            ItemDraft(
                kind=projection.kind,
                namespace=metadata["namespace"],
                name=metadata["name"],
                uid=metadata["uid"],
                owner=_owner(metadata),
                attributes=projection.attributes(
                    {name: cells[i] for name, i in index.items()}, metadata
                ),
            )
        )
    return drafts


# Reads one kind straight from the Kubernetes API (no MCP, no model).
class TableCollector:
    # ``*`` makes ``transport`` keyword-only. It lets tests substitute a fake network.
    def __init__(
        self,
        config: KubernetesApiConfig,
        projection: Projection,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self.projection = projection
        self._transport = transport  # tests only; None uses the network

    # ``async``: this can pause at each ``await`` while waiting on the network. Callers must
    # ``await`` it.
    async def collect(self, context: TrustedContext) -> Evidence:
        """List this kind in the context's namespace. Failures come back as evidence with an
        explicit error, never as an exception. ``context`` must come from the resolver."""
        collector = self.projection.collector
        # Stopwatch start, for the duration metric.
        started = time.perf_counter()
        drafts: list[ItemDraft] = []
        complete = True
        errors: list[ErrorKind] = []
        error_type = None
        # A ``with`` block that opens a trace span and closes it automatically at the end.
        with telemetry.tracer().start_as_current_span(
            f"collector.kubernetes.{self.projection.kind.lower()}s",
            kind=SpanKind.CLIENT,
            attributes={"vyom.collector": collector},
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
                    collector=collector,
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
            collector,
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
                path = self.projection.path.format(namespace=namespace)
                table = await self._page(http, path, params)
                try:
                    drafts.extend(_drafts(self.projection, table))
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


class PodCollector(TableCollector):
    """The Pod collector, as the direct pod view uses it."""

    def __init__(
        self, config: KubernetesApiConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        super().__init__(config, POD, transport=transport)
