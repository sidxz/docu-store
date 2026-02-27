"""Qdrant adapter for the unified summary_embeddings collection.

Stores both page-level and artifact-level summary embeddings in one collection.
Point ID scheme:
  - page summaries:     ``page-{page_id}``
  - artifact summaries: ``artifact-{artifact_id}``

Payload fields (indexed for filtering):
  - entity_type: "page" | "artifact"
  - entity_id:   str(UUID)
  - artifact_id: str(UUID)
"""

from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

import structlog
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.models import Distance, PointStruct, VectorParams

from application.ports.summary_vector_store import SummarySearchResult, SummaryVectorStore
from domain.value_objects.text_embedding import TextEmbedding

logger = structlog.get_logger()


def _page_point_id(page_id: UUID) -> str:
    return str(uuid5(NAMESPACE_URL, f"page:{page_id}"))


def _artifact_point_id(artifact_id: UUID) -> str:
    return str(uuid5(NAMESPACE_URL, f"artifact:{artifact_id}"))


class SummaryQdrantStore(SummaryVectorStore):
    """Qdrant adapter for the unified summary embeddings collection."""

    def __init__(
        self,
        url: str = "http://localhost:6333",
        api_key: str | None = None,
        collection_name: str = "summary_embeddings",
        vector_size: int = 384,  # all-MiniLM-L6-v2
    ) -> None:
        self.url = url
        self.api_key = api_key
        self.collection_name = collection_name
        self.vector_size = vector_size
        self._client: AsyncQdrantClient | None = None

        logger.info(
            "initializing_summary_qdrant_store",
            url=url,
            collection=collection_name,
        )

    async def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(url=self.url, api_key=self.api_key, timeout=30)
            logger.info("summary_qdrant_client_created")
        return self._client

    async def ensure_collection_exists(self) -> None:
        """Create the collection if it doesn't exist. Idempotent."""
        client = await self._get_client()

        try:
            collections = await client.get_collections()
            exists = any(c.name == self.collection_name for c in collections.collections)

            if exists:
                logger.info("summary_collection_already_exists", collection=self.collection_name)
                return

            await client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )

            # Payload indexes for efficient filtering
            for field, schema in [
                ("entity_type", models.PayloadSchemaType.KEYWORD),
                ("entity_id", models.PayloadSchemaType.KEYWORD),
                ("artifact_id", models.PayloadSchemaType.KEYWORD),
            ]:
                await client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=schema,
                )

            logger.info(
                "summary_collection_created",
                collection=self.collection_name,
                vector_size=self.vector_size,
            )

        except Exception as e:
            logger.exception(
                "failed_to_create_summary_collection",
                collection=self.collection_name,
                error=str(e),
            )
            raise

    async def upsert_page_summary_embedding(  # noqa: PLR0913
        self,
        page_id: UUID,
        artifact_id: UUID,
        embedding: TextEmbedding,
        summary_text: str,
        artifact_title: str | None = None,
        page_index: int = 0,
    ) -> None:
        client = await self._get_client()

        point_id = _page_point_id(page_id)
        payload = {
            "entity_type": "page",
            "entity_id": str(page_id),
            "artifact_id": str(artifact_id),
            "page_index": page_index,
            "summary_text": summary_text,
            "artifact_title": artifact_title,
            "model_name": embedding.model_name,
            "dimensions": embedding.dimensions,
            "generated_at": embedding.generated_at.isoformat(),
        }

        try:
            await client.upsert(
                collection_name=self.collection_name,
                points=[PointStruct(id=point_id, vector=embedding.vector, payload=payload)],
            )
            logger.info(
                "page_summary_embedding_upserted",
                page_id=str(page_id),
                artifact_id=str(artifact_id),
            )
        except Exception as e:
            logger.exception(
                "failed_to_upsert_page_summary_embedding",
                page_id=str(page_id),
                error=str(e),
            )
            raise

    async def upsert_artifact_summary_embedding(
        self,
        artifact_id: UUID,
        embedding: TextEmbedding,
        summary_text: str,
        artifact_title: str | None = None,
        page_count: int = 0,
    ) -> None:
        client = await self._get_client()

        point_id = _artifact_point_id(artifact_id)
        payload = {
            "entity_type": "artifact",
            "entity_id": str(artifact_id),
            "artifact_id": str(artifact_id),
            "page_count": page_count,
            "summary_text": summary_text,
            "artifact_title": artifact_title,
            "model_name": embedding.model_name,
            "dimensions": embedding.dimensions,
            "generated_at": embedding.generated_at.isoformat(),
        }

        try:
            await client.upsert(
                collection_name=self.collection_name,
                points=[PointStruct(id=point_id, vector=embedding.vector, payload=payload)],
            )
            logger.info(
                "artifact_summary_embedding_upserted",
                artifact_id=str(artifact_id),
            )
        except Exception as e:
            logger.exception(
                "failed_to_upsert_artifact_summary_embedding",
                artifact_id=str(artifact_id),
                error=str(e),
            )
            raise

    async def delete_page_summary(self, page_id: UUID) -> None:
        client = await self._get_client()
        try:
            await client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(points=[_page_point_id(page_id)]),
            )
            logger.info("page_summary_embedding_deleted", page_id=str(page_id))
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "failed_to_delete_page_summary_embedding",
                page_id=str(page_id),
                error=str(e),
            )

    async def delete_artifact_summary(self, artifact_id: UUID) -> None:
        client = await self._get_client()
        try:
            await client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(points=[_artifact_point_id(artifact_id)]),
            )
            logger.info("artifact_summary_embedding_deleted", artifact_id=str(artifact_id))
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "failed_to_delete_artifact_summary_embedding",
                artifact_id=str(artifact_id),
                error=str(e),
            )

    async def search_summaries(
        self,
        query_embedding: TextEmbedding,
        limit: int = 10,
        entity_type_filter: Literal["page", "artifact"] | None = None,
        artifact_id_filter: UUID | None = None,
        score_threshold: float | None = None,
    ) -> list[SummarySearchResult]:
        client = await self._get_client()

        # Build filter conditions
        must_conditions = []
        if entity_type_filter:
            must_conditions.append(
                models.FieldCondition(
                    key="entity_type",
                    match=models.MatchValue(value=entity_type_filter),
                ),
            )
        if artifact_id_filter:
            must_conditions.append(
                models.FieldCondition(
                    key="artifact_id",
                    match=models.MatchValue(value=str(artifact_id_filter)),
                ),
            )

        query_filter = models.Filter(must=must_conditions) if must_conditions else None

        try:
            search_result = await client.query_points(
                collection_name=self.collection_name,
                query=query_embedding.vector,
                query_filter=query_filter,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )
        except Exception as e:
            logger.exception("summary_search_failed", error=str(e))
            raise
        else:
            results = [
                SummarySearchResult(
                    point_id=str(point.id),
                    entity_type=point.payload["entity_type"],
                    entity_id=UUID(point.payload["entity_id"]),
                    artifact_id=UUID(point.payload["artifact_id"]),
                    score=point.score,
                    summary_text=point.payload.get("summary_text"),
                    artifact_title=point.payload.get("artifact_title"),
                    metadata=point.payload,
                )
                for point in search_result.points
            ]

            logger.info(
                "summary_search_completed",
                results_count=len(results),
                limit=limit,
                entity_type_filter=entity_type_filter,
                has_artifact_filter=artifact_id_filter is not None,
            )
            return results

    async def get_collection_info(self) -> dict:
        client = await self._get_client()
        try:
            info = await client.get_collection(collection_name=self.collection_name)
        except Exception as e:
            logger.exception(
                "failed_to_get_summary_collection_info",
                collection=self.collection_name,
                error=str(e),
            )
            raise
        else:
            return {
                "collection_name": self.collection_name,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": info.status,
                "vector_size": self.vector_size,
            }

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("summary_qdrant_client_closed")
