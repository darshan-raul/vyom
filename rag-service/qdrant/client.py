import os
from typing import Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from inference.settings import BedrockSettings
from inference.types import InferenceError

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")


def _collection_name(tenant_id: str, settings: BedrockSettings) -> str:
    settings.validate(embedding=True)
    return settings.collection_name(tenant_id)


def _get_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def _get_collection(client: QdrantClient, name: str):
    # A named GET works with the current Qdrant server. Never list collections
    # across tenants just to check existence.
    try:
        return client.get_collection(collection_name=name)
    except Exception as error:
        if getattr(error, "status_code", None) == 404:
            return None
        raise InferenceError("Vector service is unavailable") from None


def _check_collection(info, settings: BedrockSettings) -> None:
    if info is None:
        raise InferenceError("Selected embedding version is not indexed; seed or reindex required")
    vectors = info.config.params.vectors
    if isinstance(vectors, dict) or vectors.size != settings.dimensions or vectors.distance != Distance.COSINE:
        raise InferenceError("Vector collection schema is incompatible; reindex required")


def ensure_collection(tenant_id: str, *, settings: BedrockSettings) -> None:
    name = _collection_name(tenant_id, settings)
    client = _get_client()
    info = _get_collection(client, name)
    if info is None:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=settings.dimensions, distance=Distance.COSINE),
        )
        info = _get_collection(client, name)
    _check_collection(info, settings)


def upsert_chunk(
    tenant_id: str,
    chunk_id: str,
    vector: list[float],
    payload: dict,
    *,
    settings: BedrockSettings,
) -> None:
    name = _collection_name(tenant_id, settings)
    if len(vector) != settings.dimensions:
        raise InferenceError("Embedding dimension does not match collection")
    client = _get_client()
    ensure_collection(tenant_id, settings=settings)
    client.upsert(
        collection_name=name,
        points=[
            PointStruct(
                id=chunk_id,
                vector=vector,
                payload={**payload, "embedding_version": settings.vector_version},
            )
        ],
    )


def search_chunks(
    tenant_id: str,
    query_vector: list[float],
    *,
    settings: BedrockSettings,
    top_k: int = 5,
    filter_source: Optional[str] = None,
) -> list[dict]:
    name = _collection_name(tenant_id, settings)
    if len(query_vector) != settings.dimensions or not 1 <= top_k <= 50:
        raise InferenceError("Invalid retrieval dimension or result limit")
    client = _get_client()
    # Missing current vectors are explicit; no fallback to any old collection.
    _check_collection(_get_collection(client, name), settings)

    search_filter = None
    if filter_source:
        search_filter = Filter(
            must=[
                FieldCondition(
                    key="source",
                    match=MatchValue(value=filter_source),
                )
            ]
        )

    results = client.search(
        collection_name=name,
        query_vector=query_vector,
        limit=top_k,
        query_filter=search_filter,
    )

    return [
        {
            "id": hit.id,
            "score": hit.score,
            "chunk_text": hit.payload.get("chunk_text", ""),
            "source": hit.payload.get("source", ""),
            "chunk_index": hit.payload.get("chunk_index", 0),
        }
        for hit in results
    ]
