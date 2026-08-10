from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.util.config import Settings, get_settings
from src.services.llm_service import LLMService
from src.services.sparql_service import SparqlService
from src.services.lucene_service import LuceneService
from src.services.chat_service import ChatService
from src.services.health_service import HealthService
from src.services.session_service import SessionService


def get_openai_client(request: Request):
    return request.app.state.openai_client


def get_http_client(request: Request):
    return request.app.state.http_client


def get_db_sessionmaker(request: Request):
    return request.app.state.db_sessionmaker


async def get_db_session(
    sessionmaker=Depends(get_db_sessionmaker),
) -> AsyncGenerator[AsyncSession, None]:
    async with sessionmaker() as session:
        yield session


def get_llm_service(
    client=Depends(get_openai_client),
    settings: Settings = Depends(get_settings),
) -> LLMService:
    return LLMService(
        client=client,
        settings=settings,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )


def get_sparql_service(
    client=Depends(get_http_client),
    settings: Settings = Depends(get_settings),
) -> SparqlService:
    return SparqlService(client=client, settings=settings)


def get_lucene_service(
    sparql: SparqlService = Depends(get_sparql_service),
) -> LuceneService:
    return LuceneService(sparql=sparql)


def get_chat_service(
    llm: LLMService = Depends(get_llm_service),
    sparql: SparqlService = Depends(get_sparql_service),
    lucene: LuceneService = Depends(get_lucene_service),
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ChatService:
    return ChatService(llm=llm, sparql=sparql, lucene=lucene, db=db, settings=settings)


def get_health_service(
    llm: LLMService = Depends(get_llm_service),
    sparql: SparqlService = Depends(get_sparql_service),
) -> HealthService:
    return HealthService(llm=llm, sparql=sparql)


def get_session_service(
    db: AsyncSession = Depends(get_db_session),
) -> SessionService:
    return SessionService(db=db)