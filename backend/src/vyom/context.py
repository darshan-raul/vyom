"""Server-side authority for a request.

During the personal alpha one operator-configured context applies to every request. Browser
input and model output never contribute to it. S6 replaces ``FixedContextResolver`` with a
resolver that derives the context from a verified token and membership.
"""

# Protocol describes a shape ("anything with these methods") without being a real parent class.
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

# A regular expression (regex) for safe IDs: starts with a letter/digit, then up to 62 more
# letters, digits, dots, underscores or dashes. The leading ``r`` marks a "raw" string so
# backslashes are kept literally, which is what regexes want.
_ID = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$"


# Who/where a request is allowed to touch. Built only by the server, never from user input.
class TrustedContext(BaseModel):
    # frozen: cannot be modified after creation; forbid: unknown fields are an error.
    model_config = ConfigDict(frozen=True, extra="forbid")

    # ``Field(pattern=...)`` rejects any value that does not match the regex.
    workspace_id: str = Field(pattern=_ID)
    connection_id: str = Field(pattern=_ID)
    cluster_uid: str = Field(pattern=_ID)
    # Kubernetes namespace rules: lowercase letters, digits and dashes, max 63 characters.
    namespace: str = Field(pattern=r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


# Anything with a ``resolve()`` method returning a TrustedContext counts as a ContextResolver.
# The ``...`` body means "no code here": this only describes the shape.
class ContextResolver(Protocol):
    def resolve(self) -> TrustedContext: ...


class FixedContextResolver:
    """The operator-configured context, identical for every request."""

    # __init__ runs when you create the object. ``self`` is the object being built;
    # the leading underscore on ``_context`` marks it as internal.
    def __init__(self, context: TrustedContext) -> None:
        self._context = context

    # Always returns the same context. Later this will look it up from the logged-in user.
    def resolve(self) -> TrustedContext:
        return self._context
