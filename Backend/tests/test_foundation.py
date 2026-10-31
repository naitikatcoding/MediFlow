import os
import pytest

# Override DATABASE_URL to SQLite BEFORE any app imports.
# This prevents test_foundation from trying to connect to YugabyteDB cloud
# which would cause a hang or DNS failure in environments without network access.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_foundation.db")

from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoints(client):
    for endpoint in ["/health", "/api/health", "/api/v1/health"]:
        response = client.get(endpoint)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        assert data["service"] == "MediFlow"
        assert "database" in data
        assert "integrations" in data
        assert "gemini" in data["integrations"]
        assert "meko" in data["integrations"]


def test_error_response_conventions(client):
    # Test 404 error response structure
    response = client.get("/api/v1/nonexistent-route-for-testing")
    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "error"
    assert "error" in data
    assert data["error"]["code"] == 404
    assert "message" in data["error"]
