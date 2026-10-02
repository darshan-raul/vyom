import os
from fastapi import FastAPI

from routers import history, ingest, retrieve

app = FastAPI(title="Vyom RAG", version="1.0.0")

app.include_router(history.router)
app.include_router(ingest.router)
app.include_router(retrieve.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "rag-service"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)