from fastapi import FastAPI
from pydantic import BaseModel

from vyom import __version__, telemetry


class Health(BaseModel):
    status: str
    service: str
    version: str


telemetry.configure_logging()
app = FastAPI(title="Vyom API", version=__version__)
telemetry.instrument(app)


@app.get("/api/health")
def health() -> Health:
    """Process liveness only; it does not check Kubernetes, MCP or the model provider."""
    return Health(status="ok", service=telemetry.SERVICE_NAME, version=__version__)
