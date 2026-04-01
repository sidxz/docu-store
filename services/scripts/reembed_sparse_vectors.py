"""One-time script to re-embed all sparse vectors after switching to HashingVectorizer.

Reads all pages from MongoDB, generates new sparse vectors using the
HashingVectorizer, and updates existing points in Qdrant (sparse vector only,
dense vectors are untouched).

Usage:
    uv run python scripts/reembed_sparse_vectors.py
"""

from __future__ import annotations

import asyncio
from uuid import NAMESPACE_URL, uuid5

import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from qdrant_client import AsyncQdrantClient, models

from infrastructure.config import Settings
from infrastructure.embeddings.tfidf_sparse_generator import TfidfSparseGenerator
from infrastructure.text_chunkers.langchain_chunker import LangChainTextChunker

logger = structlog.get_logger()


async def main() -> None:
    settings = Settings()
    sparse_generator = TfidfSparseGenerator()
    chunker = LangChainTextChunker(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    # Connect to MongoDB
    mongo = AsyncIOMotorClient(settings.mongo_uri)
    db = mongo[settings.mongo_db]
    pages_collection = db[settings.mongo_pages_collection]

    # Connect to Qdrant
    qdrant = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )

    collection_name = settings.qdrant_collection_name

    # Verify collection exists
    try:
        info = await qdrant.get_collection(collection_name)
        logger.info("qdrant_collection_found", collection=collection_name, points=info.points_count)
    except Exception as e:
        logger.error("qdrant_collection_not_found", collection=collection_name, error=str(e))
        return

    # Read all pages with text
    cursor = pages_collection.find(
        {"text_mention.text": {"$ne": None, "$exists": True}},
        {"page_id": 1, "text_mention.text": 1, "_id": 0},
    )

    total_pages = 0
    total_points_updated = 0
    errors = 0

    async for doc in cursor:
        page_id = doc["page_id"]
        text = doc.get("text_mention", {}).get("text", "")
        if not text or not text.strip():
            continue

        total_pages += 1

        # Chunk the text (same as embedding pipeline)
        text_chunks = chunker.chunk_text(text)
        if not text_chunks:
            chunk_texts = [text]
        else:
            chunk_texts = [c.text for c in text_chunks]

        # Generate sparse embeddings for each chunk
        sparse_embeddings = sparse_generator.generate_batch_sparse_embeddings(chunk_texts)

        # Update each chunk's sparse vector in Qdrant
        points_to_update = []
        for chunk_index, sparse_emb in enumerate(sparse_embeddings):
            point_id = str(uuid5(NAMESPACE_URL, f"{page_id}:chunk:{chunk_index}"))
            points_to_update.append(
                models.PointVectors(
                    id=point_id,
                    vector={
                        "sparse": models.SparseVector(
                            indices=sparse_emb.indices,
                            values=sparse_emb.values,
                        ),
                    },
                ),
            )

        if points_to_update:
            try:
                await qdrant.update_vectors(
                    collection_name=collection_name,
                    points=points_to_update,
                )
                total_points_updated += len(points_to_update)
            except Exception as e:
                errors += 1
                logger.warning(
                    "sparse_update_failed",
                    page_id=page_id,
                    error=str(e),
                )

        if total_pages % 50 == 0:
            logger.info(
                "reembed_progress",
                pages=total_pages,
                points_updated=total_points_updated,
                errors=errors,
            )

    logger.info(
        "reembed_complete",
        total_pages=total_pages,
        total_points_updated=total_points_updated,
        errors=errors,
    )

    await qdrant.close()
    mongo.close()


if __name__ == "__main__":
    asyncio.run(main())
