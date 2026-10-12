"""The evidence contract shared by the MCP path and the direct-SDK path.

Both paths hand trusted scope, projected items and coverage to ``build_evidence``, so
identifiers, time, coverage and state mean the same thing whichever path collected them.
Nothing here holds raw upstream objects: items carry a host-chosen projection only.
"""

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from vyom.context import TrustedContext

Scalar = str | int | float | bool | None


class State(StrEnum):
    """What a consumer may conclude. These are never collapsed into one another."""

    COMPLETE = "complete"  # the source answered in full and returned at least one item
    ZERO = "zero"  # the source answered in full: nothing matches
    PARTIAL = "partial"  # some of the answer is absent (truncated or partly failed)
    STALE = "stale"  # collected longer ago than the reader's freshness budget
    DENIED = "denied"  # the source or host policy refused; says nothing about the resources
    MISSING = "missing"  # no observation was obtained (unreachable, timed out, invalid)


class ErrorKind(StrEnum):
    # Refused by host policy before any upstream call.
    TOOL_NOT_ALLOWED = "tool_not_allowed"
    SCOPE_VIOLATION = "scope_violation"
    INVALID_ARGUMENTS = "invalid_arguments"
    # Refused by the source.
    AUTH = "auth"
    FORBIDDEN = "forbidden"
    # No usable observation.
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    PROTOCOL = "protocol"
    SCHEMA_MISMATCH = "schema_mismatch"
    OVERSIZED = "oversized"
    INVALID_OUTPUT = "invalid_output"
    UPSTREAM_ERROR = "upstream_error"
    # Part of the answer was left out.
    TRUNCATED = "truncated"


_DENIED = frozenset(
    {ErrorKind.TOOL_NOT_ALLOWED, ErrorKind.SCOPE_VIOLATION, ErrorKind.AUTH, ErrorKind.FORBIDDEN}
)

# Fixed text per kind: upstream and exception messages never enter the contract.
_MESSAGES = {
    ErrorKind.TOOL_NOT_ALLOWED: "This tool is not enabled for this deployment.",
    ErrorKind.SCOPE_VIOLATION: "The request is outside the configured scope.",
    ErrorKind.INVALID_ARGUMENTS: "The tool arguments were rejected.",
    ErrorKind.AUTH: "The integration endpoint rejected Vyom's credential.",
    ErrorKind.FORBIDDEN: "The source denied access to the requested resources.",
    ErrorKind.UNAVAILABLE: "The integration endpoint could not be reached.",
    ErrorKind.TIMEOUT: "The integration did not answer within the time limit.",
    ErrorKind.PROTOCOL: "The integration endpoint did not complete the MCP exchange.",
    ErrorKind.SCHEMA_MISMATCH: "The upstream tool is missing or differs from the reviewed schema.",
    ErrorKind.OVERSIZED: "The result exceeded the configured size limit and was discarded.",
    ErrorKind.INVALID_OUTPUT: "The result did not have the expected shape and was discarded.",
    ErrorKind.UPSTREAM_ERROR: "The upstream tool reported an error.",
    ErrorKind.TRUNCATED: "The result was cut at the configured item limit.",
}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EvidenceError(_Frozen):
    kind: ErrorKind
    message: str

    @classmethod
    def of(cls, kind: ErrorKind) -> "EvidenceError":
        return cls(kind=kind, message=_MESSAGES[kind])


class McpProvenance(_Frozen):
    server_id: str
    tool_id: str
    # What the upstream reported about itself; absent when it did not say.
    upstream_name: str | None = None
    upstream_version: str | None = None
    protocol_version: str | None = None


class Source(_Frozen):
    """Who was asked, within which authority. Scope fields come from the trusted context."""

    path: Literal["mcp", "direct"]
    workspace_id: str
    connection_id: str
    cluster_uid: str
    namespace: str
    mcp: McpProvenance | None = None  # set on the MCP path only
    collector: str | None = None  # set on the direct path only


class ItemDraft(_Frozen):
    """One projected resource as a path produced it, before the host assigns identity."""

    kind: str
    namespace: str
    name: str
    uid: str | None = None
    observed_at: datetime | None = None  # the source's own timestamp; never invented
    attributes: dict[str, Scalar] = {}


class EvidenceItem(ItemDraft):
    id: str


class Coverage(_Frozen):
    complete: bool
    returned: int
    truncated: bool = False


class Evidence(_Frozen):
    id: str
    source: Source
    collected_at: datetime
    state: State
    coverage: Coverage
    items: tuple[EvidenceItem, ...] = ()
    errors: tuple[EvidenceError, ...] = ()

    def state_at(self, now: datetime, max_age: timedelta) -> State:
        """The state for a reader at ``now``: usable evidence past ``max_age`` is stale."""
        usable = self.state in (State.COMPLETE, State.ZERO, State.PARTIAL)
        return State.STALE if usable and now - self.collected_at > max_age else self.state


def resource_id(cluster_uid: str, namespace: str, kind: str, name: str) -> str:
    """Path-independent identity of a namespaced Kubernetes resource.

    Built from fields every path can supply. The object UID is carried beside it when the
    source reports one; it distinguishes incarnations but is not required for identity.
    """
    return f"k8s:{cluster_uid}:{namespace}:{kind.lower()}:{name}"


def build_evidence(
    *,
    context: TrustedContext,
    path: Literal["mcp", "direct"],
    drafts: tuple[ItemDraft, ...] | list[ItemDraft] = (),
    complete: bool = True,
    errors: tuple[ErrorKind, ...] | list[ErrorKind] = (),
    mcp: McpProvenance | None = None,
    collector: str | None = None,
    max_items: int | None = None,
    collected_at: datetime | None = None,
) -> Evidence:
    """Normalize one collection. The only constructor either path should use."""
    kinds = list(dict.fromkeys(errors))
    drafts = list(drafts)

    # A path must not return resources outside the authority it was asked under.
    if any(draft.namespace != context.namespace for draft in drafts):
        drafts, complete = [], False
        kinds.append(ErrorKind.SCOPE_VIOLATION)

    truncated = max_items is not None and len(drafts) > max_items
    if truncated:
        drafts = drafts[:max_items]
        kinds.append(ErrorKind.TRUNCATED)

    items = tuple(
        EvidenceItem(
            id=resource_id(context.cluster_uid, draft.namespace, draft.kind, draft.name),
            **draft.model_dump(),
        )
        for draft in drafts
    )
    blocking = [kind for kind in kinds if kind is not ErrorKind.TRUNCATED]
    complete = complete and not kinds

    if blocking and not items:
        state = State.DENIED if any(kind in _DENIED for kind in blocking) else State.MISSING
    elif not complete:
        state = State.PARTIAL
    elif items:
        state = State.COMPLETE
    else:
        state = State.ZERO

    return Evidence(
        id=f"ev_{uuid.uuid4().hex}",
        source=Source(
            path=path,
            workspace_id=context.workspace_id,
            connection_id=context.connection_id,
            cluster_uid=context.cluster_uid,
            namespace=context.namespace,
            mcp=mcp,
            collector=collector,
        ),
        collected_at=collected_at or datetime.now(UTC),
        state=state,
        coverage=Coverage(complete=complete, returned=len(items), truncated=truncated),
        items=items,
        errors=tuple(EvidenceError.of(kind) for kind in kinds),
    )
