"""Targeted Docling-enrichment backfill: re-parse + block-aware re-embed.

For each artifact_id: (1) ParseArtifactUseCase re-parses through Docling, writing
the enriched IR blob (captions / heading level / section_path) and refreshed page
text; (2) BatchReEmbedArtifactPagesUseCase reads that IR, chunks block-aware, and
writes the Phase-B structure payload (block_type/section_path/is_table/is_figure/
caption) into page_embeddings. Also ensures the 4 new payload indexes exist
(idempotent) so the structure filters are usable.

Runs the use cases directly in-process — no Temporal worker, no event cascade
(re-parse emits TextMentionUpdated to the event store; with no pipeline_worker
running it is not consumed, so NER/summarization do not re-run here).

Usage:
    uv run python scripts/reembed_docling_enrichment.py            # 3 pilot decks
    uv run python scripts/reembed_docling_enrichment.py <id> ...   # specific artifacts
"""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

import structlog
from qdrant_client import AsyncQdrantClient, models
from returns.result import Failure

from application.use_cases.batch_reembed_use_cases import BatchReEmbedArtifactPagesUseCase
from application.use_cases.parse_artifact_use_case import ParseArtifactUseCase
from infrastructure.config import settings
from infrastructure.di.container import create_container

logger = structlog.get_logger()

# Top-3 multi-page decks (71/63/59 pages) whose source.pdf resolves on disk.
PILOT_IDS = [
    "ecdb4b64-1406-47bf-8de3-4a47d550624d",
    "790f75df-6e91-4300-b7e3-408eb63d6083",
    "09de5c0a-3cad-45a7-985f-2f75df5f6271",
]

# Phase-B chunk-payload indexes missing from pre-existing collections.
NEW_INDEXES = [
    ("block_type", models.PayloadSchemaType.KEYWORD),
    ("section_path_normalized", models.PayloadSchemaType.KEYWORD),
    ("is_table", models.PayloadSchemaType.BOOL),
    ("is_figure", models.PayloadSchemaType.BOOL),
]


async def ensure_indexes(client: AsyncQdrantClient) -> None:
    for field, schema in NEW_INDEXES:
        await client.create_payload_index(
            collection_name=settings.qdrant_collection_name,
            field_name=field,
            field_schema=schema,
        )
        logger.info("index_ensured", collection=settings.qdrant_collection_name, field=field)


async def run(ids: list[str]) -> None:
    container = create_container()
    parse_uc = container[ParseArtifactUseCase]
    reembed_uc = container[BatchReEmbedArtifactPagesUseCase]
    client = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60)

    try:
        await ensure_indexes(client)
        for aid in ids:
            uid = UUID(aid)
            try:
                logger.info("pilot.parse_start", artifact_id=aid)
                pres = await parse_uc.execute(uid)
                if isinstance(pres, Failure):
                    logger.error("pilot.parse_failed", artifact_id=aid, error=str(pres.failure()))
                    continue
                logger.info("pilot.parse_done", artifact_id=aid, pages=len(pres.unwrap()))

                rres = await reembed_uc.execute(uid)
                logger.info("pilot.reembed_done", artifact_id=aid, result=rres)
            except Exception:
                logger.exception("pilot.artifact_failed", artifact_id=aid)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1:] or PILOT_IDS))
