from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from embed.bedrock import embeddings
from inference.types import InferenceError
from qdrant.client import search_chunks

router = APIRouter(prefix="/retrieve", tags=["retrieve"])


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    filter_source: str | None = None


class RetrieveResponse(BaseModel):
    chunks: list[dict]
    query: str


@router.post("", response_model=RetrieveResponse)
async def retrieve(
    req: RetrieveRequest,
    x_tenant_id: str = Header(..., alias="x-tenant-id"),
):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query cannot be empty")

    try:
        adapter = embeddings()
        adapter.settings.collection_name(x_tenant_id)
        vector = await adapter.embed_text(req.query)
        chunks = search_chunks(
            tenant_id=x_tenant_id,
            query_vector=vector,
            settings=adapter.settings,
            top_k=req.top_k,
            filter_source=req.filter_source,
        )
    except InferenceError:
        raise HTTPException(status_code=503, detail="Retrieval inference is unavailable") from None

    return RetrieveResponse(chunks=chunks, query=req.query)
