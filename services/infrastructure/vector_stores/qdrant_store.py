from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

import structlog
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, PointStruct, SparseVectorParams, VectorParams

from application.ports.sparse_embedding_generator import SparseEmbedding
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
        vector_size: int = 768,  # Default for nomic-embed-text-v1.5
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
        Idempotent - safe to call multiple times (handles 409 race).
        """
        client = await self._get_client()

        try:
            # Check if collection exists
            collections = await client.get_collections()
            exists = any(c.name == self.collection_name for c in collections.collections)

            if exists:
                logger.info("collection_already_exists", collection=self.collection_name)
                return

            # Create collection with named dense vector + sparse vector + quantization
            try:
                await client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config={
                        "dense": VectorParams(
                            size=self.vector_size,
                            distance=Distance.COSINE,
                        ),
                    },
                    sparse_vectors_config={
                        "sparse": SparseVectorParams(
                            modifier=models.Modifier.IDF,
                        ),
                    },
                    quantization_config=models.ScalarQuantization(
                        scalar=models.ScalarQuantizationConfig(
                            type=models.ScalarType.INT8,
                            quantile=0.99,
                            always_ram=True,
                        ),
                    ),
                )
            except UnexpectedResponse as e:
                if e.status_code == 409:
                    # Race condition: another process created it between check and create
                    logger.info(
                        "collection_created_by_another_process", collection=self.collection_name,
                    )
                    return
                raise

            # Create payload indexes for filtering
            for field, schema in [
                ("artifact_id", models.PayloadSchemaType.KEYWORD),
                ("page_id", models.PayloadSchemaType.KEYWORD),
                ("workspace_id", models.PayloadSchemaType.KEYWORD),
                ("tag_normalized", models.PayloadSchemaType.KEYWORD),
                ("entity_types", models.PayloadSchemaType.KEYWORD),
            ]:
                await client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=schema,
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
        sparse_embedding: SparseEmbedding | None = None,
    ) -> None:
        """Store or update a page embedding in Qdrant.

        Args:
            page_id: The unique ID of the page (used as point ID)
            artifact_id: The ID of the artifact this page belongs to
            embedding: The text embedding to store
            page_index: The index/position of this page in the artifact
            metadata: Optional additional metadata to store
            sparse_embedding: Optional sparse vector for hybrid search

        """
        client = await self._get_client()

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

        vector: dict = {"dense": embedding.vector}
        if sparse_embedding:
            vector["sparse"] = models.SparseVector(
                indices=sparse_embedding.indices,
                values=sparse_embedding.values,
            )

        point = PointStruct(
            id=str(page_id),
            vector=vector,
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
        sparse_embeddings: list[SparseEmbedding] | None = None,
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
            sparse_embeddings: Optional sparse vectors (one per chunk) for hybrid search

        """
        client = await self._get_client()

        # First, delete any existing chunks for this page
        await self.delete_page_embedding(page_id)

        # Build points for all chunks
        points = []
        for chunk_index, embedding in enumerate(embeddings):
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

            vector: dict = {"dense": embedding.vector}
            if sparse_embeddings and chunk_index < len(sparse_embeddings):
                se = sparse_embeddings[chunk_index]
                vector["sparse"] = models.SparseVector(
                    indices=se.indices,
                    values=se.values,
                )

            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
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
            artifact_id_filter,
            allowed_artifact_ids,
            workspace_id,
            tags,
            entity_types,
            tag_match_mode,
        )

        try:
            search_result = await client.query_points(
                collection_name=self.collection_name,
                query=query_embedding.vector,
                using="dense",
                query_filter=query_filter,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
                search_params=models.SearchParams(
                    quantization=models.QuantizationSearchParams(
                        rescore=True,
                        oversampling=2.0,
                    ),
                ),
            )
        except Exception as e:
            logger.exception("search_failed", error=str(e))
            raise
        else:
            results = self._points_to_results(search_result.points)
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
            artifact_id_filter,
            allowed_artifact_ids,
            workspace_id,
            tags,
            entity_types,
            tag_match_mode,
        )

        try:
            grouped = await client.query_points_groups(
                collection_name=self.collection_name,
                query=query_embedding.vector,
                using="dense",
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

    @staticmethod
    def _points_to_results(points: list) -> list[PageSearchResult]:
        """Convert Qdrant scored points to PageSearchResult list."""
        return [
            PageSearchResult(
                page_id=UUID(p.payload["page_id"]),
                artifact_id=UUID(p.payload["artifact_id"]),
                score=p.score,
                page_index=p.payload["page_index"],
                metadata=p.payload,
            )
            for p in points
        ]

    async def search_hybrid(  # noqa: PLR0913
        self,
        dense_query: TextEmbedding,
        sparse_query: SparseEmbedding,
        limit: int = 10,
        prefetch_limit: int = 100,
        artifact_id_filter: UUID | None = None,
        score_threshold: float | None = None,
        allowed_artifact_ids: list[UUID] | None = None,
        workspace_id: UUID | None = None,
        tags: list[str] | None = None,
        entity_types: list[str] | None = None,
        tag_match_mode: Literal["any", "all"] = "any",
    ) -> list[PageSearchResult]:
        """Hybrid search: dense + sparse, fused with Reciprocal Rank Fusion."""
        client = await self._get_client()
        query_filter = self._build_filter(
            artifact_id_filter,
            allowed_artifact_ids,
            workspace_id,
            tags,
            entity_types,
            tag_match_mode,
        )

        try:
            result = await client.query_points(
                collection_name=self.collection_name,
                prefetch=[
                    models.Prefetch(
                        query=dense_query.vector,
                        using="dense",
                        limit=prefetch_limit,
                        filter=query_filter,
                    ),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=sparse_query.indices,
                            values=sparse_query.values,
                        ),
                        using="sparse",
                        limit=prefetch_limit,
                        filter=query_filter,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )
        except Exception as e:
            logger.exception("hybrid_search_failed", error=str(e))
            raise
        else:
            results = self._points_to_results(result.points)
            logger.info(
                "hybrid_search_completed",
                results_count=len(results),
                limit=limit,
                prefetch_limit=prefetch_limit,
            )
            return results

    async def search_hybrid_grouped(  # noqa: PLR0913
        self,
        dense_query: TextEmbedding,
        sparse_query: SparseEmbedding,
        limit: int = 10,
        prefetch_limit: int = 100,
        artifact_id_filter: UUID | None = None,
        score_threshold: float | None = None,
        allowed_artifact_ids: list[UUID] | None = None,
        workspace_id: UUID | None = None,
        tags: list[str] | None = None,
        entity_types: list[str] | None = None,
        tag_match_mode: Literal["any", "all"] = "any",
        group_size: int = 1,
    ) -> list[PageSearchResult]:
        """Hybrid search with server-side dedup by page_id via RRF fusion."""
        client = await self._get_client()
        query_filter = self._build_filter(
            artifact_id_filter,
            allowed_artifact_ids,
            workspace_id,
            tags,
            entity_types,
            tag_match_mode,
        )

        try:
            grouped = await client.query_points_groups(
                collection_name=self.collection_name,
                prefetch=[
                    models.Prefetch(
                        query=dense_query.vector,
                        using="dense",
                        limit=prefetch_limit,
                        filter=query_filter,
                    ),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=sparse_query.indices,
                            values=sparse_query.values,
                        ),
                        using="sparse",
                        limit=prefetch_limit,
                        filter=query_filter,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                group_by="page_id",
                group_size=group_size,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )
        except Exception as e:
            logger.exception("hybrid_grouped_search_failed", error=str(e))
            raise
        else:
            results = []
            for group in grouped.groups:
                best = group.hits[0]
                results.append(
                    PageSearchResult(
                        page_id=UUID(best.payload["page_id"]),
                        artifact_id=UUID(best.payload["artifact_id"]),
                        score=best.score,
                        page_index=best.payload["page_index"],
                        metadata=best.payload,
                    ),
                )
            logger.info(
                "hybrid_grouped_search_completed",
                results_count=len(results),
                limit=limit,
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
