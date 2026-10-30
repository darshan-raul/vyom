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
