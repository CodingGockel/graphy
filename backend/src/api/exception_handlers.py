from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.models.events import ErrorEvent, ErrorKind
from src.models.schemas import ErrorResponse
from src.util.exceptions import (
    LLMServiceException,
    LLMNoContentException,
    SparqlDatabaseException,
    SparqlDatabaseStatusCode,
    SparqlQueryException,
    SessionNotFoundException,
    StepNotFoundException,
)
from src.util.logger import logger


def _err(status_code: int, error: str, detail: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error, detail=detail).model_dump(),
    )


# Errors inside a chat stream are sent as an `error` event instead of a status code.
# Keep in sync with the handlers below.
_STREAM_ERROR_KINDS: tuple[tuple[type[Exception], ErrorKind], ...] = (
    (LLMServiceException, "llm_unavailable"),       # 503
    (LLMNoContentException, "llm_no_content"),      # 502
    (SparqlDatabaseException, "sparql_unavailable"),  # 503
    (SparqlDatabaseStatusCode, "sparql_failed"),    # 502
    (SparqlQueryException, "sparql_failed"),        # 502
    # The route checks the session before the stream starts; this is the session
    # being deleted in between.
    (SessionNotFoundException, "session_not_found"),  # 404
)


def stream_error_event(exc: Exception) -> ErrorEvent:
    """The `error` event for an exception that ended a chat stream."""
    for exc_type, kind in _STREAM_ERROR_KINDS:
        if isinstance(exc, exc_type):
            logger.warning(f"Chat stream failed ({kind}): {exc}")
            return ErrorEvent(kind=kind, message=str(exc))
    logger.error("Unhandled exception in chat stream", exc_info=exc)
    return ErrorEvent(kind="internal", message="Internal server error")


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

    @app.exception_handler(SessionNotFoundException)
    async def _session_not_found(request: Request, exc: SessionNotFoundException):
        return _err(404, "Session not found", str(exc))

    @app.exception_handler(StepNotFoundException)
    async def _step_not_found(request: Request, exc: StepNotFoundException):
        return _err(404, "Step not found", str(exc))

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
