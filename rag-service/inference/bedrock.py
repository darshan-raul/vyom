"""Bedrock-only embedding and reasoning adapters; no provider fallback."""

import asyncio
import json
import math
from typing import Any

from .settings import BedrockSettings, REGION
from .types import InferenceError


def create_runtime_client():
    import boto3
    from botocore.config import Config

    # Explicit endpoint prevents AWS_ENDPOINT_URL environment overrides from
    # redirecting tenant content. SDK uses platform workload identity/IRSA.
    return boto3.client(
        "bedrock-runtime",
        region_name=REGION,
        endpoint_url=f"https://bedrock-runtime.{REGION}.amazonaws.com",
        config=Config(
            connect_timeout=5,
            read_timeout=45,
            retries={"mode": "standard", "total_max_attempts": 3},
        ),
    )


class BedrockEmbeddings:
    def __init__(self, settings: BedrockSettings, client: Any = None):
        settings.validate(embedding=True)
        self.settings = settings
        self._client = client

    def _embed_one(self, text: str) -> list[float]:
        self.settings.verify_approval()
        try:
            client = self._client or create_runtime_client()
            response = client.invoke_model(
                modelId=self.settings.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "inputText": text,
                    "dimensions": self.settings.dimensions,
                    "normalize": True,
                }),
            )
            body = response["body"]
            try:
                vector = json.loads(body.read())["embedding"]
            finally:
                body.close()
            if not isinstance(vector, list) or len(vector) != self.settings.dimensions:
                raise ValueError("invalid dimensions")
            if any(type(value) not in (int, float) or not math.isfinite(value) for value in vector):
                raise ValueError("invalid vector")
            if not any(value != 0 for value in vector):
                raise ValueError("zero vector")
            return vector
        except Exception:
            # Provider exception messages may contain request data. Do not chain
            # them into application logs or HTTP error bodies.
            raise InferenceError("Bedrock embedding request failed") from None

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if len(texts) > 128 or any(not text.strip() or len(text) > 50_000 for text in texts):
            raise InferenceError("Embedding batch exceeds input limits or contains blank text")
        # At most four in-flight SDK calls; gather preserves document order.
        semaphore = asyncio.Semaphore(4)

        async def embed(text: str) -> list[float]:
            async with semaphore:
                return await asyncio.to_thread(self._embed_one, text)

        return await asyncio.gather(*(embed(text) for text in texts))

    async def embed_text(self, text: str) -> list[float]:
        return (await self.embed_texts([text]))[0]


class BedrockChat:
    """Converse messages/content blocks are retained for LangGraph tool loops.

    Tool-use output is a proposal. The authenticated MCP wrapper must authorize
    it. This adapter never invokes a tool and never supplies tenant identity.
    """

    def __init__(self, settings: BedrockSettings, client: Any = None):
        settings.validate()
        self.settings = settings
        self._client = client

    def _converse(self, messages: list[dict], system: str, tool_config: dict | None, max_tokens: int) -> dict:
        self.settings.verify_approval()
        request = {
            "modelId": self.settings.model_id,
            "messages": messages,
            "inferenceConfig": {"maxTokens": max_tokens},
        }
        if system:
            request["system"] = [{"text": system}]
        if tool_config:
            request["toolConfig"] = tool_config
        try:
            client = self._client or create_runtime_client()
            response = client.converse(**request)
            return {
                "message": response["output"]["message"],
                "stop_reason": response["stopReason"],
                "usage": response.get("usage", {}),
            }
        except Exception:
            raise InferenceError("Bedrock reasoning request failed") from None

    async def converse(
        self, messages: list[dict], *, system: str = "", tool_config: dict | None = None,
        max_tokens: int = 2048,
    ) -> dict:
        if not messages or not 1 <= max_tokens <= 8192:
            raise InferenceError("Invalid reasoning request")
        return await asyncio.to_thread(self._converse, messages, system, tool_config, max_tokens)
