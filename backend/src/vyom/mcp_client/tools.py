"""Host-side definitions of the upstream tools Vyom is willing to call.

A tool is callable only when all of these hold: it has a ``ToolSpec`` here, the operator
enabled it for the server, and the server advertises it with the input schema that was
reviewed. What the upstream says about a tool (description, annotations such as
``readOnlyHint``) is never used to enable it and is never shown to the model.
"""

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

from vyom.evidence import ErrorKind, ItemDraft


class ToolArguments(BaseModel):
    """Base for a tool's typed arguments: unknown fields are rejected, not ignored."""

    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


@dataclass(frozen=True)
class ToolOutput:
    """What a projector may read from an upstream result."""

    text: str
    structured: Any = None


@dataclass(frozen=True)
class Projection:
    items: tuple[ItemDraft, ...]
    complete: bool = True


def schema_digest(input_schema: Mapping[str, Any]) -> str:
    """Stable digest of an advertised input schema, recorded when the tool is reviewed."""
    canonical = json.dumps(input_schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class ToolSpec:
    server_id: str
    name: str  # the upstream tool name
    description: str  # written by Vyom for the model; the upstream description is unused
    arguments: type[ToolArguments]
    # sha256 of the upstream input schema this spec was reviewed against.
    input_schema_sha256: str
    # Turns an upstream result into the minimal projection; raises on an unexpected shape.
    project: Callable[[ToolOutput], Projection]
    # Upstream argument name -> trusted-context field. The host supplies these; a caller
    # may omit them or repeat the trusted value, and anything else is refused.
    scope_arguments: Mapping[str, str] = field(default_factory=dict)
    max_items: int = 200
    # Reads an upstream tool error's text to tell a denial from other failures. The text
    # itself is discarded.
    error_kind: Callable[[str], ErrorKind] | None = None
