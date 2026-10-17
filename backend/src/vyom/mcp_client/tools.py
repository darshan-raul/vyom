"""Host-side definitions of the upstream tools Vyom is willing to call.

A tool is callable only when all of these hold: it has a ``ToolSpec`` here, the operator
enabled it for the server, and the server advertises it with the input schema that was
reviewed. What the upstream says about a tool (description, annotations such as
``readOnlyHint``) is never used to enable it and is never shown to the model.
"""

import hashlib  # hash functions (sha256)
import json
from collections.abc import Callable, Mapping  # type names: "a function" / "a dict-like"

# @dataclass auto-writes __init__ for a class that is mostly named fields;
# ``field`` customises one of those fields.
from dataclasses import dataclass, field
from typing import Any  # "any type at all"

from pydantic import BaseModel, ConfigDict

from vyom.evidence import ErrorKind, ItemDraft


# Each tool defines its own subclass listing the arguments it accepts.
class ToolArguments(BaseModel):
    """Base for a tool's typed arguments: unknown fields are rejected, not ignored."""

    # strict: no silent type conversion ("5" is not accepted for an int);
    # hide_input_in_errors: error messages don't repeat the bad value back.
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


# frozen=True: instances cannot be changed after creation.
@dataclass(frozen=True)
class ToolOutput:
    """What a projector may read from an upstream result."""

    text: str  # the plain-text reply from the tool
    structured: Any = None  # the parsed JSON reply, if the tool sent one


@dataclass(frozen=True)
class Projection:
    # The "projection": only the fields Vyom chose to keep, as a tuple of drafts.
    items: tuple[ItemDraft, ...]
    complete: bool = True


def schema_digest(input_schema: Mapping[str, Any]) -> str:
    """Stable digest of an advertised input schema, recorded when the tool is reviewed."""
    # sort_keys + compact separators give the same text for the same schema, so the hash
    # only changes when the schema's content changes.
    canonical = json.dumps(input_schema, sort_keys=True, separators=(",", ":"))
    # encode() turns text into bytes (what hashing needs); hexdigest() gives readable hex.
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class ToolSpec:
    # A fully reviewed description of one tool Vyom may call.
    server_id: str
    name: str  # the upstream tool name
    description: str  # written by Vyom for the model; the upstream description is unused
    arguments: type[ToolArguments]  # the class itself (not an instance) that validates inputs
    # sha256 of the upstream input schema this spec was reviewed against.
    input_schema_sha256: str
    # Turns an upstream result into the minimal projection; raises on an unexpected shape.
    project: Callable[[ToolOutput], Projection]
    # Upstream argument name -> trusted-context field. The host supplies these; a caller
    # may omit them or repeat the trusted value, and anything else is refused.
    # default_factory=dict: each ToolSpec gets its own fresh empty dict. (A plain ``= {}``
    # default would be shared, a classic Python trap, so dataclasses forbid it.)
    scope_arguments: Mapping[str, str] = field(default_factory=dict)
    max_items: int = 200
    # Reads an upstream tool error's text to tell a denial from other failures. The text
    # itself is discarded.
    # ``Callable[[str], ErrorKind]`` = a function taking a string and returning an ErrorKind.
    error_kind: Callable[[str], ErrorKind] | None = None
