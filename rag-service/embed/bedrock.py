"""RAG facade: one model specification for both ingest and retrieval."""

from inference.bedrock import BedrockEmbeddings
from inference.settings import BedrockSettings


def embeddings() -> BedrockEmbeddings:
    return BedrockEmbeddings(BedrockSettings.from_env("embedding"))
