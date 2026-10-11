from fastapi.testclient import TestClient

from vyom import __version__
from vyom.api.app import app


def test_health_reports_service_and_version():
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "vyom-api", "version": __version__}
