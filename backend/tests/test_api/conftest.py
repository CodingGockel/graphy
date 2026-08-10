import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    """Plain TestClient (NOT entered as a context manager) so the app's `lifespan`
    — which builds real OpenAI/httpx/DB clients and runs a startup health check —
    does not run. Endpoint dependencies are replaced via `app.dependency_overrides`."""
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()
