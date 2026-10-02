from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
from openai import AsyncOpenAI

from src.db.database import init_db
from src.services.llm_service import LLMService
from src.services.sparql_service import SparqlService
from src.services.health_service import HealthService
from src.api.v1.chat import router as chat_router
from src.api.v1.health import router as health_router
from src.api.v1.info import router as info_router
from src.api.v1.sessions import router as sessions_router
from src.api.exception_handlers import register_exception_handlers
from src.util.config import get_settings
from src.util.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    #init settings
    settings = get_settings()

    #init openapi client for llm requests
    app.state.openai_client = AsyncOpenAI(
        api_key=settings.blablador_api_key,
        base_url=settings.blablador_base_url,
    )

    #init httpx client for sparql requests
    app.state.http_client = httpx.AsyncClient(timeout=settings.sparql_timeout)

    #init database
    engine, app.state.db_sessionmaker = await init_db(settings.database_url)
    logger.info("Database initialized")

    logger.info("Server started")

    #do health check on server startup
    llm = LLMService(client=app.state.openai_client, settings=settings)
    sparql = SparqlService(client=app.state.http_client, settings=settings)
    health = await HealthService(llm=llm, sparql=sparql).process()

    if health.status != "ok":
        logger.error(f"Startup healthcheck failed: {health.error}")
    else:
        logger.info("Startup healthcheck passed")

    try:
        yield
    finally:
        await app.state.http_client.aclose()
        await app.state.openai_client.close()
        await engine.dispose()
        logger.info("Server shutdown")


app = FastAPI(
    lifespan=lifespan,
    title="Data Explorer API",
    version="1.0.0",
)

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")
app.include_router(sessions_router, prefix="/api/v1")
app.include_router(info_router, prefix="/api/v1")