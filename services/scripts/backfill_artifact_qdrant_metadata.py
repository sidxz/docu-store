"""One-time backfill: sync artifact-level metadata to Qdrant payloads.

Reads all artifact_ids from the MongoDB read model and calls
SyncArtifactMetadataToVectorStoreUseCase for each, which writes
``artifact_tag_normalized`` (authors, aggregated tags, year) to both
page_embeddings and summary_embeddings collections.

Also ensures the ``artifact_tag_normalized`` payload index exists on both
Qdrant collections.

Usage:
    uv run python scripts/backfill_artifact_qdrant_metadata.py
"""

from __future__ import annotations

import asyncio

import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from qdrant_client import AsyncQdrantClient, models

from application.use_cases.vector_metadata_use_cases import SyncArtifactMetadataToVectorStoreUseCase
from infrastructure.config import settings
from infrastructure.di.container import create_container

logger = structlog.get_logger()


async def ensure_payload_indexes() -> None:
    """Create artifact_tag_normalized index on both collections (idempotent)."""
    client = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=30)
    try:
        for collection in [
            settings.qdrant_collection_name,
            settings.qdrant_summary_collection_name,
        ]:
            await client.create_payload_index(
                collection_name=collection,
                field_name="artifact_tag_normalized",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            logger.info(
                "payload_index_created", collection=collection, field="artifact_tag_normalized"
            )
    finally:
        await client.close()


async def backfill() -> None:
    container = create_container()
    use_case = container[SyncArtifactMetadataToVectorStoreUseCase]

    # Ensure indexes exist first
    await ensure_payload_indexes()

    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db]

    count = 0
    errors = 0
    async for doc in db[settings.mongo_artifacts_collection].find({}, {"artifact_id": 1}):
        artifact_id_str = doc.get("artifact_id")
        if not artifact_id_str:
            continue
        try:
            from uuid import UUID

            await use_case.execute(UUID(artifact_id_str))
            count += 1
            if count % 50 == 0:
                logger.info("backfill_progress", processed=count)
        except Exception:
            errors += 1
            logger.exception("backfill_error", artifact_id=artifact_id_str)

    logger.info("backfill_complete", total=count, errors=errors)


if __name__ == "__main__":
    asyncio.run(backfill())
