from concurrent.futures import ThreadPoolExecutor
import pytest

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_engine


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


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


def test_repeated_health_requests_return_all_connections_to_pool(client):
    for _ in range(25):
        response = client.get("/health")
        assert response.status_code == 200

    assert get_engine().pool.checkedout() == 0


def test_concurrent_health_requests_do_not_exhaust_or_leak_pool_connections(client):
    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(executor.map(lambda _: client.get("/health"), range(60)))

    assert all(response.status_code == 200 for response in responses)
    assert get_engine().pool.checkedout() == 0


def test_error_response_conventions(client):
    # Test 404 error response structure
    response = client.get("/api/v1/nonexistent-route-for-testing")
    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "error"
    assert "error" in data
    assert data["error"]["code"] == 404
    assert "message" in data["error"]
