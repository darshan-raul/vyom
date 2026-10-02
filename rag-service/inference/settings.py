"""Fail-closed operator configuration, separate from tenant request input."""

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from .types import ConfigurationError

REGION = "ap-south-1"
TITAN_V2 = "amazon.titan-embed-text-v2:0"
# Foundation IDs only: profiles, ARNs, Marketplace endpoints and prompt routers
# are deliberately not accepted, even if accidentally added to the allowlist.
FOUNDATION_ID = re.compile(
    r"(?:amazon|anthropic|cohere|meta|mistral|ai21|deepseek|qwen|nvidia)\.[a-z0-9][a-z0-9.:-]*"
)


@dataclass(frozen=True)
class BedrockSettings:
    model_id: str
    allowed_models: tuple[str, ...]
    region: str = REGION
    policy_file: str = "/etc/secrets/bedrock-policy.json"
    dimensions: int = 1024

    def validate(self, *, embedding: bool = False) -> None:
        if self.region != REGION:
            raise ConfigurationError("Bedrock region must be ap-south-1")
        if not FOUNDATION_ID.fullmatch(self.model_id):
            raise ConfigurationError("Only direct Bedrock foundation model IDs are permitted")
        if self.model_id not in self.allowed_models:
            raise ConfigurationError("Bedrock model is not allowlisted")
        if embedding and (self.model_id != TITAN_V2 or self.dimensions not in (256, 512, 1024)):
            raise ConfigurationError("Unsupported embedding codec or dimensions")

    def verify_approval(self) -> None:
        """Read the B3.5 deployment attestation before each invocation.

        This does not configure AWS or establish ZDR itself. B3.5 must verify the
        actual account policy, IAM, regional model access, and logging settings.
        """
        try:
            policy = json.loads(Path(self.policy_file).read_text())
            approved = (
                policy["region"] == REGION
                and policy["data_retention_mode"] == "none"
                and policy["invocation_content_logging"] is False
                and isinstance(policy["approved_models"], list)
                and self.model_id in policy["approved_models"]
            )
        except (OSError, ValueError, KeyError, TypeError):
            raise ConfigurationError("Bedrock deployment approval is missing or invalid") from None
        if not approved:
            raise ConfigurationError("Bedrock deployment policy denies inference")

    @property
    def vector_version(self) -> str:
        # Include codec, model, normalization, dimensions and metric. Same-sized
        # embeddings from another model must not silently share a collection.
        spec = f"v1|titan-v2|{self.model_id}|{self.dimensions}|normalize=true|cosine"
        return hashlib.sha256(spec.encode()).hexdigest()[:16]

    def collection_name(self, tenant_id: str) -> str:
        try:
            tenant = str(UUID(tenant_id))
        except (ValueError, TypeError, AttributeError):
            raise ConfigurationError("Invalid tenant identifier") from None
        return f"rag-{tenant}-v1-{self.vector_version}"

    @classmethod
    def from_env(cls, purpose: str) -> "BedrockSettings":
        if purpose not in ("embedding", "chat"):
            raise ConfigurationError("Unknown Bedrock purpose")
        try:
            dimensions = int(os.getenv("BEDROCK_EMBEDDING_DIMENSIONS", "1024"))
        except ValueError:
            raise ConfigurationError("Invalid embedding dimensions") from None
        prefix = f"BEDROCK_{purpose.upper()}"
        settings = cls(
            model_id=os.getenv(f"{prefix}_MODEL_ID", ""),
            allowed_models=tuple(
                item.strip() for item in os.getenv(f"{prefix}_ALLOWED_MODELS", "").split(",") if item.strip()
            ),
            region=os.getenv("BEDROCK_REGION", REGION),
            policy_file=os.getenv("BEDROCK_POLICY_FILE", "/etc/secrets/bedrock-policy.json"),
            dimensions=dimensions,
        )
        settings.validate(embedding=purpose == "embedding")
        return settings
