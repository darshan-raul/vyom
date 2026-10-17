"""The evidence contract shared by the MCP path and the direct-SDK path.

Both paths hand trusted scope, projected items and coverage to ``build_evidence``, so
identifiers, time, coverage and state mean the same thing whichever path collected them.
Nothing here holds raw upstream objects: items carry a host-chosen projection only.
"""

# --- Imports ---------------------------------------------------------------------------
# ``import x`` loads a whole module; ``from x import y`` loads just one name out of it.
import uuid  # makes random unique IDs
from datetime import UTC, datetime, timedelta  # date/time types; UTC is the timezone
from enum import StrEnum  # a fixed set of named string values (see ``State`` below)
from typing import Literal  # a type that only allows specific exact values

# pydantic is a third-party library that validates data against type hints.
# BaseModel = a class whose fields are type-checked; ConfigDict = settings for that class.
from pydantic import BaseModel, ConfigDict

from vyom.context import TrustedContext

# A type alias: ``Scalar`` is just a short name for "one plain value". The ``|`` means "or",
# so a Scalar is a string, int, float, bool, or None (Python's "no value").
Scalar = str | int | float | bool | None


# ``class State(StrEnum)`` makes an enum: a closed list of allowed values. Using ``State.ZERO``
# instead of the raw string "zero" avoids typos, and an editor can list every option.
class State(StrEnum):
    """What a consumer may conclude. These are never collapsed into one another."""

    COMPLETE = "complete"  # the source answered in full and returned at least one item
    ZERO = "zero"  # the source answered in full: nothing matches
    PARTIAL = "partial"  # some of the answer is absent (truncated or partly failed)
    STALE = "stale"  # collected longer ago than the reader's freshness budget
    DENIED = "denied"  # the source or host policy refused; says nothing about the resources
    MISSING = "missing"  # no observation was obtained (unreachable, timed out, invalid)


class ErrorKind(StrEnum):
    # Every way a collection can go wrong, as a fixed list instead of free-form error text.
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


# A leading underscore means "private to this file". A frozenset is a set (unique items, fast
# ``in`` checks) that cannot be changed after creation. These are the errors that count as
# "someone said no" rather than "something broke".
_DENIED = frozenset(
    {ErrorKind.TOOL_NOT_ALLOWED, ErrorKind.SCOPE_VIOLATION, ErrorKind.AUTH, ErrorKind.FORBIDDEN}
)

# Fixed text per kind: upstream and exception messages never enter the contract.
# (A dict maps a key to a value; here each ErrorKind maps to its safe, fixed message.)
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


# Base class for every model below. ``frozen=True``: objects can't be changed after they are
# created. ``extra="forbid"``: passing a field the class doesn't declare is an error.
# Subclasses inherit both settings, so they are written once here.
class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EvidenceError(_Frozen):
    # In a pydantic model, ``name: type`` declares a field. Both are required (no default).
    kind: ErrorKind
    message: str

    # @classmethod: the method belongs to the class, not one instance, and receives the class
    # as ``cls``. This one is an alternate constructor: ``EvidenceError.of(kind)`` fills in
    # the fixed message so callers cannot supply their own text.
    @classmethod
    def of(cls, kind: ErrorKind) -> "EvidenceError":
        return cls(kind=kind, message=_MESSAGES[kind])


class McpProvenance(_Frozen):
    server_id: str
    tool_id: str
    # What the upstream reported about itself; absent when it did not say.
    # ``str | None = None`` means "a string, or None, and None if not given".
    upstream_name: str | None = None
    upstream_version: str | None = None
    protocol_version: str | None = None


class Source(_Frozen):
    """Who was asked, within which authority. Scope fields come from the trusted context."""

    # ``Literal["mcp", "direct"]``: the value must be exactly one of these two strings.
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
    # A dict of text keys to plain values, e.g. {"status": "Running", "restarts": 0}.
    # ``= {}`` is the default (pydantic copies it for each object, unlike a plain function).
    attributes: dict[str, Scalar] = {}


# Inherits every field from ItemDraft and adds ``id``, assigned later by ``build_evidence``.
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
    # ``tuple[X, ...]`` is an immutable sequence of any length holding X; ``()`` is empty.
    items: tuple[EvidenceItem, ...] = ()
    errors: tuple[EvidenceError, ...] = ()

    # A method on the model; ``self`` is the Evidence object it is called on.
    def state_at(self, now: datetime, max_age: timedelta) -> State:
        """The state for a reader at ``now``: usable evidence past ``max_age`` is stale."""
        # Usable means it carries real data (complete, zero results, or partial).
        usable = self.state in (State.COMPLETE, State.ZERO, State.PARTIAL)
        # Subtracting two datetimes gives a timedelta (a duration) that can be compared.
        # ``A if condition else B`` is Python's one-line if/else.
        return State.STALE if usable and now - self.collected_at > max_age else self.state


def resource_id(cluster_uid: str, namespace: str, kind: str, name: str) -> str:
    """Path-independent identity of a namespaced Kubernetes resource.

    Built from fields every path can supply. The object UID is carried beside it when the
    source reports one; it distinguishes incarnations but is not required for identity.
    """
    # An f-string: text in {} is replaced by that value, e.g. "k8s:abc:default:pod:web-1".
    return f"k8s:{cluster_uid}:{namespace}:{kind.lower()}:{name}"


# The bare ``*`` below means every parameter after it must be passed by name, e.g.
# ``build_evidence(context=ctx, path="mcp")``. That keeps the many options readable.
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
    # ``dict.fromkeys(errors)`` is a trick to drop duplicates while keeping order
    # (dict keys are unique and remember insertion order).
    kinds = list(dict.fromkeys(errors))
    drafts = list(drafts)

    # A path must not return resources outside the authority it was asked under.
    # ``any(...)`` is True if at least one item matches the condition.
    if any(draft.namespace != context.namespace for draft in drafts):
        # Tuple assignment: discard every item and mark the result incomplete in one line.
        drafts, complete = [], False
        kinds.append(ErrorKind.SCOPE_VIOLATION)

    truncated = max_items is not None and len(drafts) > max_items
    if truncated:
        drafts = drafts[:max_items]  # slicing: keep only the first ``max_items`` entries
        kinds.append(ErrorKind.TRUNCATED)

    # Build one EvidenceItem per draft. ``**draft.model_dump()`` unpacks the draft's fields
    # into keyword arguments, and we add the host-computed ``id`` alongside them.
    items = tuple(
        EvidenceItem(
            id=resource_id(context.cluster_uid, draft.namespace, draft.kind, draft.name),
            **draft.model_dump(),
        )
        for draft in drafts
    )
    # Truncation alone is not a failure; every other error blocks a trustworthy answer.
    # ``is not`` compares identity, the usual way to compare enum members.
    blocking = [kind for kind in kinds if kind is not ErrorKind.TRUNCATED]
    complete = complete and not kinds

    # Decide the single state. Order matters: the first matching branch wins.
    if blocking and not items:
        # Failed and nothing to show: "denied" if someone refused, otherwise "missing".
        state = State.DENIED if any(kind in _DENIED for kind in blocking) else State.MISSING
    elif not complete:
        state = State.PARTIAL
    elif items:
        state = State.COMPLETE
    else:
        state = State.ZERO

    return Evidence(
        id=f"ev_{uuid.uuid4().hex}",  # random unique ID, e.g. "ev_3f9a..."
        source=Source(
            path=path,
            workspace_id=context.workspace_id,
            connection_id=context.connection_id,
            cluster_uid=context.cluster_uid,
            namespace=context.namespace,
            mcp=mcp,
            collector=collector,
        ),
        # ``a or b``: use ``a`` if it has a value, otherwise ``b`` (here: the current UTC time).
        collected_at=collected_at or datetime.now(UTC),
        state=state,
        coverage=Coverage(complete=complete, returned=len(items), truncated=truncated),
        items=items,
        errors=tuple(EvidenceError.of(kind) for kind in kinds),
    )
