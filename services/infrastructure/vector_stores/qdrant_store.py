from uuid import UUID

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
    ):
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

            logger.info(
                "collection_created",
                collection=self.collection_name,
                vector_size=self.vector_size,
            )

        except Exception as e:
            logger.error(
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
            logger.error(
                "failed_to_upsert_embedding",
                page_id=str(page_id),
                error=str(e),
            )
            raise

    async def delete_page_embedding(self, page_id: UUID) -> None:
        """Delete a page embedding from Qdrant.

        Args:
            page_id: The ID of the page to delete

        Idempotent - no error if page doesn't exist.

        """
        client = await self._get_client()

        try:
            await client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(
                    points=[str(page_id)],
                ),
            )

            logger.info("embedding_deleted", page_id=str(page_id))

        except Exception as e:
            logger.warning(
                "failed_to_delete_embedding",
                page_id=str(page_id),
                error=str(e),
            )
            # Don't raise - deletion is idempotent

    async def search_similar_pages(
        self,
        query_embedding: TextEmbedding,
        limit: int = 10,
        artifact_id_filter: UUID | None = None,
        score_threshold: float | None = None,
    ) -> list[PageSearchResult]:
        """Find pages similar to the query embedding using cosine similarity.

        Args:
            query_embedding: The embedding to search for
            limit: Maximum number of results to return
            artifact_id_filter: Optional filter to search within a specific artifact
            score_threshold: Optional minimum similarity score (0.0 to 1.0)

        Returns:
            List of PageSearchResult, ordered by similarity (highest first)

        """
        client = await self._get_client()

        # Build filter if artifact_id is provided
        query_filter = None
        if artifact_id_filter:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="artifact_id",
                        match=models.MatchValue(value=str(artifact_id_filter)),
                    ),
                ],
            )

        # Note: sentence-transformers embeddings are already L2-normalized
        # Using them as-is ensures optimal similarity calculations in Qdrant
        try:
            # Use the modern Query API via query_points
            search_result = await client.query_points(
                collection_name=self.collection_name,
                query=query_embedding.vector,
                query_filter=query_filter,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )

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
                min_score=min((r.score for r in results), default=0.0),
                max_score=max((r.score for r in results), default=0.0),
            )

            return results

        except Exception as e:
            logger.error(
                "search_failed",
                error=str(e),
                exc_info=True,
            )
            raise

    async def get_collection_info(self) -> dict:
        """Get information about the collection.

        Returns:
            Dictionary with stats like vector count, dimensions, etc.

        """
        client = await self._get_client()

        try:
            info = await client.get_collection(collection_name=self.collection_name)

            return {
                "collection_name": self.collection_name,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": info.status,
                "vector_size": self.vector_size,
            }

        except Exception as e:
            logger.error(
                "failed_to_get_collection_info",
                collection=self.collection_name,
                error=str(e),
            )
            raise

    async def close(self) -> None:
        """Close the Qdrant client connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("qdrant_client_closed")
