"""Direct read of pods from the Kubernetes API, for the deterministic resource view.

Independent of MCP: its own endpoint configuration, its own credential (a ServiceAccount
other than the MCP server's) and no shared code path with the MCP host beyond the evidence
contract. It asks the API server for its Table rendering with object metadata only, so pod
specs (and the literal environment values in them) are never sent to Vyom; readiness, status
and restarts are the same values `kubectl get pods` prints.
"""

import ssl
import time
from typing import Any
from urllib.parse import urlsplit

import httpx
from opentelemetry.trace import SpanKind, StatusCode
from pydantic import BaseModel, ConfigDict, Field, field_validator

from vyom import telemetry
from vyom.context import TrustedContext
from vyom.credentials import CredentialUnavailable, check_reference, read_credential
from vyom.evidence import ErrorKind, Evidence, ItemDraft, build_evidence

COLLECTOR = "kubernetes-pods"  # source identity in evidence, and the telemetry label
_TABLE = "application/json;as=Table;g=meta.k8s.io;v=v1"
_COLUMNS = ("Name", "Ready", "Status", "Restarts")
_PAGE_SIZE = 100
_MAX_PAGES = 20


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
    max_items: int = Field(default=500, gt=0, le=2000)

    @field_validator("url")
    @classmethod
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


class _Failure(Exception):
    def __init__(self, kind: ErrorKind) -> None:
        super().__init__(kind.value)
        self.kind = kind


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


def _classify(error: Exception) -> ErrorKind:
    """Map a failure to a kind. Exception text is never used."""
    if isinstance(error, _Failure):
        return error.kind
    if isinstance(error, CredentialUnavailable):
        return ErrorKind.AUTH
    if isinstance(error, TimeoutError | httpx.TimeoutException):
        return ErrorKind.TIMEOUT
    if isinstance(error, httpx.TransportError | OSError):
        return ErrorKind.UNAVAILABLE
    return ErrorKind.INVALID_OUTPUT


def _drafts(table: Any) -> list[ItemDraft]:
    """Project one Table page. Raises on any shape other than the expected one."""
    names = [column["name"] for column in table["columnDefinitions"]]
    index = {name: names.index(name) for name in _COLUMNS}
    drafts = []
    for row in table["rows"]:
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


class PodCollector:
    def __init__(
        self, config: KubernetesApiConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._config = config
        self._transport = transport  # tests only; None uses the network

    async def collect(self, context: TrustedContext) -> Evidence:
        """List the pods in the context's namespace. Failures come back as evidence with an
        explicit error, never as an exception. ``context`` must come from the resolver."""
        started = time.perf_counter()
        drafts: list[ItemDraft] = []
        complete = True
        errors: list[ErrorKind] = []
        error_type = None
        with telemetry.tracer().start_as_current_span(
            "collector.kubernetes.pods",
            kind=SpanKind.CLIENT,
            attributes={"vyom.collector": COLLECTOR},
        ) as span:
            try:
                if self._config.connection_id != context.connection_id:
                    raise _Failure(ErrorKind.SCOPE_VIOLATION)
                complete = await self._list(context.namespace, drafts)
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

    async def _list(self, namespace: str, drafts: list[ItemDraft]) -> bool:
        """Append every page to ``drafts``. Returns False if the list was cut short."""
        config = self._config
        token = read_credential(config.credential_ref)
        verify: ssl.SSLContext | bool = True
        if config.ca_file:
            verify = ssl.create_default_context(cafile=config.ca_file)
        transport = self._transport or httpx.AsyncHTTPTransport(verify=verify)
        params: dict[str, str | int] = {"limit": _PAGE_SIZE, "includeObject": "Metadata"}
        async with httpx.AsyncClient(
            transport=transport,
            base_url=config.url,
            headers={"Authorization": f"Bearer {token}", "Accept": _TABLE},
            timeout=httpx.Timeout(config.timeout_seconds, connect=5),
            trust_env=False,
        ) as http:
            for _ in range(_MAX_PAGES):
                table = await self._page(http, f"/api/v1/namespaces/{namespace}/pods", params)
                try:
                    drafts.extend(_drafts(table))
                    token_next = table["metadata"].get("continue")
                except Exception:
                    raise _Failure(ErrorKind.INVALID_OUTPUT) from None
                if not token_next:
                    return True
                if len(drafts) > config.max_items:
                    return False  # build_evidence cuts at the limit and records the truncation
                params = {**params, "continue": token_next}
        return False

    async def _page(self, http: httpx.AsyncClient, path: str, params: dict) -> Any:
        async with http.stream("GET", path, params=params) as response:
            if response.status_code != 200:
                raise _Failure(_kind_for_status(response.status_code))
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > self._config.max_response_bytes:
                    raise _Failure(ErrorKind.OVERSIZED)
        try:
            return httpx.Response(200, content=bytes(body)).json()
        except ValueError:
            raise _Failure(ErrorKind.INVALID_OUTPUT) from None
