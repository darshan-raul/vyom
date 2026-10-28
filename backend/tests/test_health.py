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


def test_production_mode_refuses_the_development_identity():
    import pytest

    from vyom.api.app import DevelopmentIdentityRefused, create_app

    with pytest.raises(DevelopmentIdentityRefused):
        create_app(None, mode="production")


def test_unknown_mode_is_refused():
    import pytest

    from vyom.api.app import create_app

    with pytest.raises(ValueError):
        create_app(None, mode="staging")


def test_unset_mode_in_the_environment_means_production():
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "VYOM_MODE"}
    result = subprocess.run(
        [sys.executable, "-c", "import vyom.api.app"], env=env, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "DevelopmentIdentityRefused" in result.stderr
