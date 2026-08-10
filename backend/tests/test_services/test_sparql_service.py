from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.services.sparql_service import SparqlService
from src.util.exceptions import (
    SparqlDatabaseException,
    SparqlDatabaseStatusCode,
    SparqlQueryException,
)


def _make_service(settings_stub, *, get=None):
    client = MagicMock()
    # health_check uses GET, execute uses POST — wire both to the same mock so the
    # `get=` arg drives whichever verb the method under test calls.
    mock = get if get is not None else AsyncMock()
    client.get = mock
    client.post = mock
    return SparqlService(client=client, settings=settings_stub), client


def _response(status_code: int, text: str = ""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


class TestEndpoint:
    def test_builds_repository_url(self, settings_stub):
        service, _ = _make_service(settings_stub)
        assert service.endpoint == "http://graphdb.test/repositories/testrepo"


class TestExecute:
    async def test_returns_body_on_200(self, settings_stub):
        service, _ = _make_service(
            settings_stub, get=AsyncMock(return_value=_response(200, "RESULTS"))
        )
        assert await service.execute("SELECT ?s WHERE { ?s ?p ?o }") == "RESULTS"

    async def test_rejects_mutating_query_before_request(self, settings_stub):
        service, client = _make_service(settings_stub)
        with pytest.raises(SparqlQueryException):
            await service.execute("INSERT DATA { <a> <b> <c> }")
        client.get.assert_not_called()

    async def test_http_400_raises_query_exception(self, settings_stub):
        service, _ = _make_service(
            settings_stub, get=AsyncMock(return_value=_response(400, "parse error"))
        )
        with pytest.raises(SparqlQueryException):
            await service.execute("SELECT ?s WHERE { ?s ?p ?o }")

    async def test_other_non_200_raises_status_code(self, settings_stub):
        service, _ = _make_service(
            settings_stub, get=AsyncMock(return_value=_response(500, "boom"))
        )
        with pytest.raises(SparqlDatabaseStatusCode):
            await service.execute("SELECT ?s WHERE { ?s ?p ?o }")

    async def test_transport_error_raises_database_exception(self, settings_stub):
        service, _ = _make_service(
            settings_stub, get=AsyncMock(side_effect=httpx.ConnectError("refused"))
        )
        with pytest.raises(SparqlDatabaseException):
            await service.execute("SELECT ?s WHERE { ?s ?p ?o }")


class TestHealthCheck:
    async def test_ok_on_200(self, settings_stub):
        service, _ = _make_service(
            settings_stub, get=AsyncMock(return_value=_response(200))
        )
        health = await service.health_check()
        assert health.status == "ok"

    @pytest.mark.parametrize("code", [401, 403])
    async def test_auth_error_is_down(self, settings_stub, code):
        service, _ = _make_service(
            settings_stub, get=AsyncMock(return_value=_response(code))
        )
        health = await service.health_check()
        assert health.status == "down"
        assert "auth error" in health.error

    async def test_404_is_repository_not_found(self, settings_stub):
        service, _ = _make_service(
            settings_stub, get=AsyncMock(return_value=_response(404))
        )
        health = await service.health_check()
        assert health.status == "down"
        assert health.error == "repository not found"

    async def test_timeout_is_down(self, settings_stub):
        service, _ = _make_service(
            settings_stub, get=AsyncMock(side_effect=httpx.TimeoutException("slow"))
        )
        health = await service.health_check()
        assert health.status == "down"
        assert "timeout" in health.error

    async def test_unexpected_exception_is_down(self, settings_stub):
        service, _ = _make_service(
            settings_stub, get=AsyncMock(side_effect=RuntimeError("x"))
        )
        health = await service.health_check()
        assert health.status == "down"
        assert health.error == "RuntimeError"
