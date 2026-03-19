from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

import structlog
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.models import Distance, PointStruct, VectorParams

from application.ports.vector_store import PageSearchResult, VectorStore
from domain.value_objects.text_embedding import TextEmbedding

logger = structlog.get_logger()


class QdrantStore(VectorStore):
    """Adapter for Qdrant vector database.

    This implements the VectorStore port using Qdrant as the backend.
    Supports both local and cloud deployments.
    """

    def __init__(
        self,
        url: str = "http://localhost:6333",
        api_key: str | None = None,
        collection_name: str = "page_embeddings",
        vector_size: int = 384,  # Default for all-MiniLM-L6-v2
    ) -> None:
        """Initialize Qdrant client.

        Args:
            url: Qdrant server URL (local or cloud)
            api_key: API key for cloud deployment (None for local)
            collection_name: Name of the collection to use
            vector_size: Dimension of the embedding vectors

        """
        self.url = url
        self.api_key = api_key
        self.collection_name = collection_name
        self.vector_size = vector_size

        logger.info(
            "initializing_qdrant_client",
            url=url,
            collection=collection_name,
            has_api_key=api_key is not None,
        )

        # Lazy initialization
        self._client: AsyncQdrantClient | None = None

    async def _get_client(self) -> AsyncQdrantClient:
        """Get or create async Qdrant client."""
        if self._client is None:
            self._client = AsyncQdrantClient(
                url=self.url,
                api_key=self.api_key,
                timeout=30,
            )
            logger.info("qdrant_client_created")
        return self._client

    async def ensure_collection_exists(self) -> None:
        """Ensure the collection exists with proper schema.

        Creates the collection if it doesn't exist.
        Idempotent - safe to call multiple times.
        """
        client = await self._get_client()

        try:
            # Check if collection exists
            collections = await client.get_collections()
            exists = any(c.name == self.collection_name for c in collections.collections)

            if exists:
                logger.info("collection_already_exists", collection=self.collection_name)
                return

            # Create collection with cosine similarity
            await client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,  # Cosine similarity for text embeddings
                ),
            )

            # Create index on artifact_id for filtering
            await client.create_payload_index(
                collection_name=self.collection_name,
                field_name="artifact_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

            # Create index on page_id for chunk-level filtering/deletion
            await client.create_payload_index(
                collection_name=self.collection_name,
                field_name="page_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

            # Create index on workspace_id for tenant isolation
            await client.create_payload_index(
                collection_name=self.collection_name,
                field_name="workspace_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

            # Create indexes for tag-based filtering
            await client.create_payload_index(
                collection_name=self.collection_name,
                field_name="tag_normalized",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            await client.create_payload_index(
                collection_name=self.collection_name,
                field_name="entity_types",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

            logger.info(
                "collection_created",
                collection=self.collection_name,
                vector_size=self.vector_size,
            )

        except Exception as e:
            logger.exception(
                "failed_to_create_collection",
                collection=self.collection_name,
                error=str(e),
            )
            raise

    async def upsert_page_embedding(
        self,
        page_id: UUID,
        artifact_id: UUID,
        embedding: TextEmbedding,
        page_index: int,
        metadata: dict | None = None,
    ) -> None:
        """Store or update a page embedding in Qdrant.

        Args:
            page_id: The unique ID of the page (used as point ID)
            artifact_id: The ID of the artifact this page belongs to
            embedding: The text embedding to store
            page_index: The index/position of this page in the artifact
            metadata: Optional additional metadata to store

        """
        client = await self._get_client()

        # Prepare payload (metadata stored alongside vector)
        payload = {
            "page_id": str(page_id),
            "artifact_id": str(artifact_id),
            "page_index": page_index,
            "embedding_id": str(embedding.embedding_id),
            "model_name": embedding.model_name,
            "dimensions": embedding.dimensions,
            "generated_at": embedding.generated_at.isoformat(),
        }

        if metadata:
            payload.update(metadata)

        # workspace_id comes from metadata (passed by use case)
        # Already included via payload.update(metadata) above

        # Note: sentence-transformers embeddings are already L2-normalized
        # Using them as-is ensures optimal similarity calculations in Qdrant
        point = PointStruct(
            id=str(page_id),
            vector=embedding.vector,
            payload=payload,
        )

        try:
            await client.upsert(
                collection_name=self.collection_name,
                points=[point],
            )

            logger.info(
                "embedding_upserted",
                page_id=str(page_id),
                artifact_id=str(artifact_id),
            )

        except Exception as e:
            logger.exception(
                "failed_to_upsert_embedding",
                page_id=str(page_id),
                error=str(e),
            )
            raise

    async def upsert_page_chunk_embeddings(  # noqa: PLR0913
        self,
        page_id: UUID,
        artifact_id: UUID,
        embeddings: list[TextEmbedding],
        page_index: int,
        chunk_count: int,
        metadata: dict | None = None,
    ) -> None:
        """Store embeddings for multiple chunks of a single page.

        Each chunk is stored as a separate point with ID: {page_id}_chunk_{index}.
        First deletes any existing chunks for this page, then inserts new ones.

        Args:
            page_id: The unique ID of the page
            artifact_id: The ID of the artifact this page belongs to
            embeddings: List of embeddings, one per chunk (ordered by chunk index)
            page_index: The index/position of this page in the artifact
            chunk_count: Total number of chunks for this page
            metadata: Optional additional metadata to store

        """
        client = await self._get_client()

        # First, delete any existing chunks for this page
        await self.delete_page_embedding(page_id)

        # Build points for all chunks
        points = []
        for chunk_index, embedding in enumerate(embeddings):
            # Qdrant requires UUID or int IDs — generate a deterministic UUID
            # from (page_id, chunk_index) so it's reproducible
            point_id = str(uuid5(NAMESPACE_URL, f"{page_id}:chunk:{chunk_index}"))

            payload = {
                "page_id": str(page_id),
                "artifact_id": str(artifact_id),
                "page_index": page_index,
                "chunk_index": chunk_index,
                "chunk_count": chunk_count,
                "embedding_id": str(embedding.embedding_id),
                "model_name": embedding.model_name,
                "dimensions": embedding.dimensions,
                "generated_at": embedding.generated_at.isoformat(),
            }

            if metadata:
                payload.update(metadata)

            # workspace_id comes from metadata (passed by use case)

            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding.vector,
                    payload=payload,
                ),
            )

        try:
            await client.upsert(
                collection_name=self.collection_name,
                points=points,
            )

            logger.info(
                "chunk_embeddings_upserted",
                page_id=str(page_id),
                artifact_id=str(artifact_id),
                chunk_count=chunk_count,
            )

        except Exception as e:
            logger.exception(
                "failed_to_upsert_chunk_embeddings",
                page_id=str(page_id),
                chunk_count=chunk_count,
                error=str(e),
            )
            raise

    async def delete_page_embedding(self, page_id: UUID) -> None:
        """Delete a page embedding from Qdrant.

        Deletes both the legacy single-point format (id=page_id)
        and the chunk-based format (payload page_id filter).

        Args:
            page_id: The ID of the page to delete

        Idempotent - no error if page doesn't exist.

        """
        client = await self._get_client()

        try:
            # Delete legacy single-point format
            await client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(
                    points=[str(page_id)],
                ),
            )

            # Delete all chunk points for this page (by payload filter)
            await client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="page_id",
                                match=models.MatchValue(value=str(page_id)),
                            ),
                        ],
                    ),
                ),
            )

            logger.info("embedding_deleted", page_id=str(page_id))

        except Exception as e:  # noqa: BLE001
            logger.warning(
                "failed_to_delete_embedding",
                page_id=str(page_id),
                error=str(e),
            )
            # Don't raise - deletion is idempotent

    def _build_tag_conditions(
        self,
        tags: list[str] | None = None,
        entity_types: list[str] | None = None,
        tag_match_mode: Literal["any", "all"] = "any",
    ) -> list[models.Condition]:
        """Build Qdrant filter conditions for tag-based filtering."""
        conditions: list[models.Condition] = []
        if tags:
            normalized = [t.lower() for t in tags]
            if tag_match_mode == "any":
                conditions.append(
                    models.FieldCondition(
                        key="tag_normalized",
                        match=models.MatchAny(any=normalized),
                    ),
                )
            else:
                for tag in normalized:
                    conditions.append(
                        models.FieldCondition(
                            key="tag_normalized",
                            match=models.MatchValue(value=tag),
                        ),
                    )
        if entity_types:
            conditions.append(
                models.FieldCondition(
                    key="entity_types",
                    match=models.MatchAny(any=entity_types),
                ),
            )
        return conditions

    def _build_filter(  # noqa: PLR0913
        self,
        artifact_id_filter: UUID | None = None,
        allowed_artifact_ids: list[UUID] | None = None,
        workspace_id: UUID | None = None,
        tags: list[str] | None = None,
        entity_types: list[str] | None = None,
        tag_match_mode: Literal["any", "all"] = "any",
    ) -> models.Filter | None:
        """Build a combined Qdrant filter from all filter parameters."""
        must_conditions: list[models.Condition] = []
        if artifact_id_filter:
            must_conditions.append(
                models.FieldCondition(
                    key="artifact_id",
                    match=models.MatchValue(value=str(artifact_id_filter)),
                ),
            )
        if allowed_artifact_ids is not None:
            must_conditions.append(
                models.FieldCondition(
                    key="artifact_id",
                    match=models.MatchAny(any=[str(aid) for aid in allowed_artifact_ids]),
                ),
            )
        if workspace_id:
            must_conditions.append(
                models.FieldCondition(
                    key="workspace_id",
                    match=models.MatchValue(value=str(workspace_id)),
                ),
            )
        must_conditions.extend(self._build_tag_conditions(tags, entity_types, tag_match_mode))
        return models.Filter(must=must_conditions) if must_conditions else None

    async def search_similar_pages(  # noqa: PLR0913
        self,
        query_embedding: TextEmbedding,
        limit: int = 10,
        artifact_id_filter: UUID | None = None,
        score_threshold: float | None = None,
        allowed_artifact_ids: list[UUID] | None = None,
        workspace_id: UUID | None = None,
        tags: list[str] | None = None,
        entity_types: list[str] | None = None,
        tag_match_mode: Literal["any", "all"] = "any",
    ) -> list[PageSearchResult]:
        """Find pages similar to the query embedding using cosine similarity.

        Returns raw chunk-level results (may contain multiple chunks per page).
        For deduplicated page-level results, use search_pages_grouped() instead.
        """
        client = await self._get_client()
        query_filter = self._build_filter(
            artifact_id_filter, allowed_artifact_ids, workspace_id,
            tags, entity_types, tag_match_mode,
        )

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
            logger.exception("search_failed", error=str(e))
            raise
        else:
            results = [
                PageSearchResult(
                    page_id=UUID(point.payload["page_id"]),
                    artifact_id=UUID(point.payload["artifact_id"]),
                    score=point.score,
                    page_index=point.payload["page_index"],
                    metadata=point.payload,
                )
                for point in search_result.points
            ]

            logger.info(
                "search_completed",
                results_count=len(results),
                limit=limit,
                has_filter=artifact_id_filter is not None,
            )
            return results

    async def search_pages_grouped(  # noqa: PLR0913
        self,
        query_embedding: TextEmbedding,
        limit: int = 10,
        artifact_id_filter: UUID | None = None,
        score_threshold: float | None = None,
        allowed_artifact_ids: list[UUID] | None = None,
        workspace_id: UUID | None = None,
        tags: list[str] | None = None,
        entity_types: list[str] | None = None,
        tag_match_mode: Literal["any", "all"] = "any",
        group_size: int = 1,
    ) -> list[PageSearchResult]:
        """Search with server-side deduplication by page_id.

        Uses Qdrant's query_groups() to return the best-scoring chunk per page,
        eliminating application-level 3x over-fetch and dedup.

        Args:
            group_size: Number of hits to keep per page (default 1 = best chunk only).
            (other args same as search_similar_pages)

        """
        client = await self._get_client()
        query_filter = self._build_filter(
            artifact_id_filter, allowed_artifact_ids, workspace_id,
            tags, entity_types, tag_match_mode,
        )

        try:
            grouped = await client.query_points_groups(
                collection_name=self.collection_name,
                query=query_embedding.vector,
                group_by="page_id",
                group_size=group_size,
                limit=limit,
                query_filter=query_filter,
                score_threshold=score_threshold,
                with_payload=True,
            )
        except Exception as e:
            logger.exception("grouped_search_failed", error=str(e))
            raise
        else:
            results = []
            for group in grouped.groups:
                best_point = group.hits[0]
                results.append(
                    PageSearchResult(
                        page_id=UUID(best_point.payload["page_id"]),
                        artifact_id=UUID(best_point.payload["artifact_id"]),
                        score=best_point.score,
                        page_index=best_point.payload["page_index"],
                        metadata=best_point.payload,
                    ),
                )

            logger.info(
                "grouped_search_completed",
                results_count=len(results),
                limit=limit,
                has_filter=artifact_id_filter is not None,
            )
            return results

    async def get_collection_info(self) -> dict:
        """Get information about the collection.

        Returns:
            Dictionary with stats like vector count, dimensions, etc.

        """
        client = await self._get_client()

        try:
            info = await client.get_collection(collection_name=self.collection_name)
        except Exception as e:
            logger.exception(
                "failed_to_get_collection_info",
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

    async def set_page_payload(
        self,
        page_id: UUID,
        payload: dict,
    ) -> None:
        """Patch payload fields on all points for a given page without re-embedding."""
        client = await self._get_client()
        try:
            await client.set_payload(
                collection_name=self.collection_name,
                payload=payload,
                points=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="page_id",
                                match=models.MatchValue(value=str(page_id)),
                            ),
                        ],
                    ),
                ),
            )
            logger.info("page_payload_updated", page_id=str(page_id), fields=list(payload.keys()))
        except Exception as e:  # noqa: BLE001
            logger.warning("failed_to_set_page_payload", page_id=str(page_id), error=str(e))

    async def close(self) -> None:
        """Close the Qdrant client connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("qdrant_client_closed")
