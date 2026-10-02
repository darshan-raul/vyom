"""Vyom v1 transport contracts.

These models define values crossing browser/API, agent, MCP, provider, and
worker boundaries. They are deliberately provider-neutral and do not make
tenant identity caller-controlled: services construct ``TenantContext`` only
after validating a token and resolving a server-side membership.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

API_VERSION = "v1"


class ContractModel(BaseModel):
    """Base configuration shared by every v1 wire contract."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class Provider(str, Enum):
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    SIMULATED_AWS = "simulated_aws"


class ConnectionStatus(str, Enum):
    DRAFT = "draft"
    VALIDATING = "validating"
    ACTIVE = "active"
    DEGRADED = "degraded"
    DISABLED = "disabled"
    FAILED = "failed"


class UserIdentity(ContractModel):
    """Verified identity claims; ``sub`` identifies a user, never a tenant."""

    sub: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    display_name: str | None = Field(default=None, max_length=255)
    issued_at: datetime | None = None
    expires_at: datetime | None = None


class TenantContext(ContractModel):
    """Server-resolved request context. Never deserialize this from client input."""

    tenant_id: UUID
    user_id: UUID
    role: Role
    membership_id: UUID


class ProviderConnection(ContractModel):
    id: UUID
    provider: Provider
    status: ConnectionStatus
    display_name: str = Field(min_length=1, max_length=255)
    account_id: str | None = Field(default=None, max_length=255)
    default_region: str | None = Field(default=None, max_length=64)
    validated_at: datetime | None = None
    freshness_at: datetime | None = None


class ProviderError(ContractModel):
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False
    provider: Provider | None = None
    account_id: str | None = Field(default=None, max_length=255)
    region: str | None = Field(default=None, max_length=64)


ResultData = TypeVar("ResultData")


class ProviderResult(ContractModel, Generic[ResultData]):
    """Normalized provider response, including partial-result evidence."""

    data: ResultData
    provider: Provider
    retrieved_at: datetime
    freshness_at: datetime | None = None
    partial: bool = False
    errors: list[ProviderError] = Field(default_factory=list)
    next_cursor: str | None = Field(default=None, max_length=2048)

    @field_validator("errors")
    @classmethod
    def errors_require_partial(cls, errors: list[ProviderError], info: Any) -> list[ProviderError]:
        if errors and not info.data.get("partial", False):
            raise ValueError("errors require partial=true")
        return errors


class CloudEvent(ContractModel):
    """Normalized event metadata; raw provider payloads are intentionally excluded."""

    id: UUID
    source: str = Field(min_length=1, max_length=255)
    type: str = Field(min_length=1, max_length=255)
    subject: str | None = Field(default=None, max_length=512)
    occurred_at: datetime
    received_at: datetime
    provider: Provider
    account_id: str | None = Field(default=None, max_length=255)
    region: str | None = Field(default=None, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=255)
    correlation_id: UUID | None = None
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class Citation(ContractModel):
    id: UUID
    source_type: Literal["provider_result", "curated_runbook"]
    source_id: str = Field(min_length=1, max_length=512)
    title: str = Field(min_length=1, max_length=512)
    retrieved_at: datetime
    excerpt: str | None = Field(default=None, max_length=1000)
    url: str | None = Field(default=None, max_length=2048)


class ApiErrorCode(str, Enum):
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    VALIDATION = "validation"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    PROVIDER_FAILURE = "provider_failure"
    INTERNAL = "internal"


class ApiError(ContractModel):
    code: ApiErrorCode
    message: str = Field(min_length=1, max_length=500)
    request_id: UUID
    retryable: bool = False
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ApiErrorEnvelope(ContractModel):
    api_version: Literal["v1"] = API_VERSION
    error: ApiError
