from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.models.schemas import ErrorResponse
from src.util.exceptions import (
    LLMServiceException,
    LLMNoContentException,
    SparqlDatabaseException,
    SparqlDatabaseStatusCode,
    SparqlQueryException,
)
from src.util.logger import logger


def _err(status_code: int, error: str, detail: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error, detail=detail).model_dump(),
    )


def register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(LLMServiceException)
    async def _llm_unavailable(request: Request, exc: LLMServiceException):
        logger.warning(f"LLM service unavailable: {exc}")
        return _err(503, "LLM service unavailable", str(exc))

    @app.exception_handler(LLMNoContentException)
    async def _llm_no_content(request: Request, exc: LLMNoContentException):
        logger.warning(f"LLM returned no content: {exc}")
        return _err(502, "LLM returned no content", str(exc))

    @app.exception_handler(SparqlDatabaseException)
    async def _sparql_unavailable(request: Request, exc: SparqlDatabaseException):
        logger.warning(f"SPARQL endpoint unavailable: {exc}")
        return _err(503, "SPARQL endpoint unavailable", str(exc))

    @app.exception_handler(SparqlDatabaseStatusCode)
    async def _sparql_bad_status(request: Request, exc: SparqlDatabaseStatusCode):
        logger.warning(f"SPARQL query failed: {exc}")
        return _err(502, "SPARQL query failed", str(exc))

    # On maleformed sparql query we feed back to llm to improve its query
    @app.exception_handler(SparqlQueryException)
    async def _sparql_query_invalid(request: Request, exc: SparqlQueryException):
        logger.warning(f"SPARQL query invalid: {exc}")
        return _err(502, "SPARQL query failed", str(exc))

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException):
        return _err(exc.status_code, "Request failed", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return _err(422, "Validation error", str(exc.errors()))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled exception")
        return _err(500, "Internal server error")
