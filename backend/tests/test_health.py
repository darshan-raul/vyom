# TestClient calls the app in-process, so no real server or network is needed.
from fastapi.testclient import TestClient

from vyom import __version__
from vyom.api.app import app


# pytest runs every function whose name starts with ``test_``. A plain ``assert`` that
# is false makes the test fail.
def test_health_reports_service_and_version():
    # Pretend to be a browser: GET /api/health.
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "vyom-api", "version": __version__}
