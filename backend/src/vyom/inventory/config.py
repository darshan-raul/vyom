"""PostgreSQL database configuration via a server-side credential reference."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vyom.credentials import check_reference, read_credential


class DatabaseConfig(BaseModel):
    """Reference to a PostgreSQL database credential: 'file:/path' or 'env:NAME'."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    credential_ref: str
    connect_timeout_seconds: float = Field(default=5.0, gt=0, le=30)

    @field_validator("credential_ref")
    @classmethod
    def _reference_only(cls, ref: str) -> str:
        return check_reference(ref)

    def read_connection_string(self) -> str:
        """Resolve the credential reference to a connection string or URL."""
        return read_credential(self.credential_ref)


class SweepConfig(BaseModel):
    """The scheduled inventory sweep (R3.2). Absent from the operator file: no sweep runs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    interval_seconds: float = Field(default=60, ge=5, le=3600)
    # A failing kind waits interval * 2^failures, capped here, before it is collected again.
    max_backoff_seconds: float = Field(default=900, ge=5, le=86_400)
    # How long a worker holds a connection's sweep without renewing it; another worker may
    # take over after this. Must outlast one kind's collection (collector timeouts are 60 s).
    lease_seconds: float = Field(default=120, ge=10, le=3600)
