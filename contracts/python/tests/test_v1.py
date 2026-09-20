from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cloud_compass_contracts.v1 import (
    API_VERSION,
    ApiError,
    ApiErrorCode,
    ApiErrorEnvelope,
    CloudEvent,
    ConnectionStatus,
    Provider,
    ProviderConnection,
    ProviderError,
    ProviderResult,
    Role,
    TenantContext,
)


def test_tenant_context_requires_server_resolved_fields() -> None:
    context = TenantContext(
        tenant_id=uuid4(), user_id=uuid4(), membership_id=uuid4(), role=Role.VIEWER
    )
    assert context.role is Role.VIEWER

    with pytest.raises(ValidationError):
        TenantContext(tenant_id=uuid4(), user_id=uuid4(), role=Role.VIEWER)


def test_provider_result_exposes_partial_failures_explicitly() -> None:
    result = ProviderResult[list[str]](
        data=["resource-1"],
        provider=Provider.AWS,
        retrieved_at=datetime.now(timezone.utc),
        partial=True,
        errors=[ProviderError(code="access_denied", message="Denied", retryable=False)],
    )
    assert result.partial is True
    assert result.errors[0].code == "access_denied"

    with pytest.raises(ValidationError, match="partial"):
        ProviderResult[list[str]](
            data=[],
            provider=Provider.AWS,
            retrieved_at=datetime.now(timezone.utc),
            errors=[ProviderError(code="throttled", message="Retry", retryable=True)],
        )


def test_event_contract_excludes_raw_payloads() -> None:
    event = CloudEvent(
        id=uuid4(),
        source="aws.cloudtrail",
        type="aws.cloudtrail.management",
        occurred_at=datetime.now(timezone.utc),
        received_at=datetime.now(timezone.utc),
        provider=Provider.AWS,
        idempotency_key="event-123",
    )
    assert "payload" not in event.model_dump()

    with pytest.raises(ValidationError):
        CloudEvent(
            **event.model_dump(), payload={"unsafe": "raw provider event"}
        )


def test_connection_and_error_envelope_are_versioned() -> None:
    connection = ProviderConnection(
        id=uuid4(),
        provider=Provider.SIMULATED_AWS,
        status=ConnectionStatus.ACTIVE,
        display_name="Fixture AWS",
    )
    assert connection.status is ConnectionStatus.ACTIVE

    envelope = ApiErrorEnvelope(
        error=ApiError(
            code=ApiErrorCode.FORBIDDEN,
            message="Access denied",
            request_id=uuid4(),
        )
    )
    assert envelope.api_version == API_VERSION


def test_hand_maintained_typescript_contract_has_matching_version_and_exports() -> None:
    typescript_contract = (
        Path(__file__).resolve().parents[3] / "app" / "src" / "contracts" / "v1.ts"
    ).read_text()
    assert 'CONTRACT_VERSION = "v1"' in typescript_contract
    for model_name in (
        "UserIdentity",
        "TenantContext",
        "ProviderConnection",
        "ProviderResult",
        "CloudEvent",
        "Citation",
        "ApiErrorEnvelope",
    ):
        assert f"export interface {model_name}" in typescript_contract
