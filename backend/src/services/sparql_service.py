import httpx
from src.util.config import Settings
from src.util.exceptions import (
    SparqlDatabaseException,
    SparqlDatabaseStatusCode,
    SparqlQueryException,
)
from src.util.sparql_utils import validate_query
from src.models.schemas import ServiceHealth


# The health check is polled by the frontend; it must not wait for a full query timeout.
HEALTH_CHECK_TIMEOUT = 5.0


class SparqlService:
    def __init__(self, client: httpx.AsyncClient, settings: Settings, timeout: float | None = None):
        self._client = client
        self._settings = settings
        self.timeout = timeout if timeout is not None else settings.sparql_timeout
        self.headers = {
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    @property
    def endpoint(self) -> str:
        return f"{self._settings.graphdb_base_url}/repositories/{self._settings.graphdb_repository}"

    async def execute(self, query: str) -> str:
        if not validate_query(query):
            raise SparqlQueryException(
                "Query rejected: contains a forbidden operation "
                "(INSERT/DELETE/CONSTRUCT/DROP). Only SELECT/ASK queries are allowed."
            )

        try:
            response = await self._client.post(
                self.endpoint,
                headers=self.headers,
                data={"query": query},
                timeout=self.timeout,
            )
            
            if response.status_code == 400:
                raise SparqlQueryException(
                    f"GraphDB rejected the query (HTTP 400): {response.text[:500]}"
                )

            if response.status_code != 200:
                raise SparqlDatabaseStatusCode(
                    message=f"HTTP {response.status_code}: {response.text[:500]}"
                )

            return response.text

        except (SparqlDatabaseStatusCode, SparqlQueryException):
            raise
        except Exception as e:
            raise SparqlDatabaseException(str(e)) from e

    async def health_check(self) -> ServiceHealth:
        attr = {"endpoint": self.endpoint}

        try:
            response = await self._client.get(
                self.endpoint,
                headers=self.headers,
                params={"query": "ASK {}"},
                timeout=HEALTH_CHECK_TIMEOUT,
            )

        except httpx.TimeoutException:
            return ServiceHealth(
                status="down",
                error=f"timeout after {HEALTH_CHECK_TIMEOUT}s",
                additional_attributes=attr,
            )

        except Exception as e:
            return ServiceHealth(
                status="down",
                error=type(e).__name__,
                additional_attributes=attr,
            )

        if response.status_code == 200:
            return ServiceHealth(
                status="ok",
                additional_attributes=attr,
            )

        if response.status_code in (401, 403):
            return ServiceHealth(
                status="down",
                error=f"auth error: HTTP {response.status_code}",
                additional_attributes=attr,
            )

        if response.status_code == 404:
            return ServiceHealth(
                status="down",
                error="repository not found",
                additional_attributes=attr,
            )

        return ServiceHealth(
            status="down",
            error=f"HTTP {response.status_code}",
            additional_attributes=attr,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def execute_update(self, query: str) -> None:
        """Run a SPARQL update (used for Lucene index setup). Raises
        SparqlDatabaseException on a non-2xx status or transport error, mirroring
        execute(); returns None on success."""
        try:
            response = await self._client.post(
                f"{self.endpoint}/statements",
                content=query,
                headers={
                    "Content-Type": "application/sparql-update"
                },
                timeout=self.timeout,
            )
        except Exception as e:
            raise SparqlDatabaseException(str(e)) from e

        if response.status_code not in (200, 204):
            raise SparqlDatabaseException(
                f"HTTP {response.status_code}: {response.text[:500]}"
            )
