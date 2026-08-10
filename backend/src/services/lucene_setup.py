"""Standalone script: (re)create the GraphDB Lucene indices backing entity resolution.

    cd backend
    source .swep-venv/bin/activate
    python -m src.services.lucene_setup
"""
import asyncio

import httpx

from src.services.lucene_service import LuceneService
from src.services.sparql_service import SparqlService
from src.util.config import get_settings


async def main() -> None:
    client = httpx.AsyncClient(timeout=60.0)
    sparql = SparqlService(client=client, settings=get_settings(), timeout=60.0)
    service = LuceneService(sparql=sparql)
    try:
        result = await service.setup_all_indices()
        print(result)
    finally:
        await sparql.aclose()


if __name__ == "__main__":
    asyncio.run(main())
