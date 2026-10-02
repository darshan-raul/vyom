import uuid
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from embed.bedrock import embeddings
from embed.text import chunk_text
from inference.types import InferenceError
from qdrant.client import upsert_chunk, ensure_collection

router = APIRouter(prefix="/ingest", tags=["ingest"])


class IngestRequest(BaseModel):
    source: str
    source_type: str = "upload"
    content: str


class IngestResponse(BaseModel):
    document_id: str
    chunks_ingested: int


@router.post("", response_model=IngestResponse)
async def ingest(
    req: IngestRequest,
    x_tenant_id: str = Header(..., alias="x-tenant-id"),
):
    if req.source_type not in ("upload", "scraped", "builtin"):
        raise HTTPException(status_code=400, detail="source_type must be upload, scraped, or builtin")

    document_id = str(uuid.uuid4())
    chunks = chunk_text(req.content)
    if not chunks:
        raise HTTPException(status_code=400, detail="content produced no chunks")

    try:
        adapter = embeddings()
        collection = adapter.settings.collection_name(x_tenant_id)
        vectors = await adapter.embed_texts(chunks)
        ensure_collection(x_tenant_id, settings=adapter.settings)
    except InferenceError:
        raise HTTPException(status_code=503, detail="Embedding inference is unavailable") from None

    for i, (chunk_text_value, vector) in enumerate(zip(chunks, vectors)):
        chunk_id = str(uuid.uuid5(uuid.UUID(document_id), str(i)))
        payload = {
            "chunk_text": chunk_text_value,
            "source": req.source,
            "source_type": req.source_type,
            "chunk_index": i,
            "document_id": document_id,
        }
        upsert_chunk(x_tenant_id, chunk_id, vector, payload, settings=adapter.settings)

    conn = _get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rag_documents (id, tenant_id, source, source_type, chunk_count, qdrant_collection)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (document_id, x_tenant_id, req.source, req.source_type, len(chunks), collection),
            )
        conn.commit()
    finally:
        conn.close()

    return IngestResponse(document_id=document_id, chunks_ingested=len(chunks))


def _get_db():
    import psycopg2
    import os
    return psycopg2.connect(os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/cccdb"))
