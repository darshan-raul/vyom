"""Server-side authority for a request.

During the personal alpha one operator-configured context applies to every request. Browser
input and model output never contribute to it. S6 replaces ``FixedContextResolver`` with a
resolver that derives the context from a verified token and membership.
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

_ID = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$"


class TrustedContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    workspace_id: str = Field(pattern=_ID)
    connection_id: str = Field(pattern=_ID)
    cluster_uid: str = Field(pattern=_ID)
    namespace: str = Field(pattern=r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


class ContextResolver(Protocol):
    def resolve(self) -> TrustedContext: ...


class FixedContextResolver:
    """The operator-configured context, identical for every request."""

    def __init__(self, context: TrustedContext) -> None:
        self._context = context

    def resolve(self) -> TrustedContext:
        return self._context
