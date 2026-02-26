from uuid import NAMESPACE_URL, UUID, uuid5

import structlog
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.models import Distance, PointStruct, VectorParams

from application.ports.compound_vector_store import CompoundSearchResult, CompoundVectorStore
from domain.value_objects.text_embedding import TextEmbedding

logger = structlog.get_logger()


class CompoundQdrantStore(CompoundVectorStore):
    """Qdrant adapter for compound SMILES vector storage.

    Stores one point per CompoundMention per page.
    Uses a dedicated collection separate from the page text embeddings.
    Vector dimension matches ChemBERTa-77M-MTR output (384).
    """

    VECTOR_SIZE = 384

    def __init__(
        self,
        url: str = "http://localhost:6333",
        api_key: str | None = None,
        collection_name: str = "compound_embeddings",
    ) -> None:
        self.url = url
        self.api_key = api_key
        self.collection_name = collection_name

        logger.info(
            "initializing_compound_qdrant_store",
            url=url,
            collection=collection_name,
        )

        self._client: AsyncQdrantClient | None = None

    async def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(
                url=self.url,
                api_key=self.api_key,
                timeout=30,
            )
            logger.info("compound_qdrant_client_created")
        return self._client

    async def ensure_compound_collection_exists(self) -> None:
        """Create the compound collection if it does not exist."""
        client = await self._get_client()

        try:
            collections = await client.get_collections()
            exists = any(c.name == self.collection_name for c in collections.collections)

            if exists:
                logger.info("compound_collection_already_exists", collection=self.collection_name)
                return

            await client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )

            # Payload indices for efficient filtering
            await client.create_payload_index(
                collection_name=self.collection_name,
                field_name="page_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            await client.create_payload_index(
                collection_name=self.collection_name,
                field_name="artifact_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            await client.create_payload_index(
                collection_name=self.collection_name,
                field_name="canonical_smiles",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

            logger.info(
                "compound_collection_created",
                collection=self.collection_name,
                vector_size=self.VECTOR_SIZE,
            )

        except Exception as e:
            logger.exception(
                "failed_to_create_compound_collection",
                collection=self.collection_name,
                error=str(e),
            )
            raise

    async def upsert_compound_embeddings(
        self,
        page_id: UUID,
        artifact_id: UUID,
        page_index: int,
        compounds: list[dict],
        embeddings: list[TextEmbedding],
    ) -> None:
        """Delete existing compound points for the page, then insert the new ones."""
        client = await self._get_client()

        await self.delete_compound_embeddings_for_page(page_id)

        points = []
        for idx, (compound, embedding) in enumerate(zip(compounds, embeddings, strict=True)):
            point_id = str(uuid5(NAMESPACE_URL, f"{page_id}:compound:{idx}"))

            payload = {
                "page_id": str(page_id),
                "artifact_id": str(artifact_id),
                "page_index": page_index,
                "compound_index": idx,
                "smiles": compound.get("smiles", ""),
                "canonical_smiles": compound.get("canonical_smiles"),
                "extracted_id": compound.get("extracted_id"),
                "confidence": compound.get("confidence"),
                "is_smiles_valid": compound.get("is_smiles_valid"),
                "embedding_id": str(embedding.embedding_id),
                "model_name": embedding.model_name,
                "generated_at": embedding.generated_at.isoformat(),
            }

            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding.vector,
                    payload=payload,
                ),
            )

        if not points:
            return

        try:
            await client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            logger.info(
                "compound_embeddings_upserted",
                page_id=str(page_id),
                artifact_id=str(artifact_id),
                count=len(points),
            )
        except Exception as e:
            logger.exception(
                "failed_to_upsert_compound_embeddings",
                page_id=str(page_id),
                count=len(points),
                error=str(e),
            )
            raise

    async def delete_compound_embeddings_for_page(self, page_id: UUID) -> None:
        """Delete all compound embedding points belonging to a page."""
        client = await self._get_client()

        try:
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
            logger.info("compound_embeddings_deleted_for_page", page_id=str(page_id))
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "failed_to_delete_compound_embeddings",
                page_id=str(page_id),
                error=str(e),
            )

    async def search_similar_compounds(
        self,
        query_embedding: TextEmbedding,
        limit: int = 10,
        artifact_id_filter: UUID | None = None,
        score_threshold: float | None = None,
    ) -> list[CompoundSearchResult]:
        """Find compounds by SMILES structural similarity."""
        client = await self._get_client()

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
            logger.exception("compound_search_failed", error=str(e))
            raise
        else:
            results = [
                CompoundSearchResult(
                    page_id=UUID(point.payload["page_id"]),
                    artifact_id=UUID(point.payload["artifact_id"]),
                    score=point.score,
                    page_index=point.payload["page_index"],
                    smiles=point.payload["smiles"],
                    canonical_smiles=point.payload.get("canonical_smiles"),
                    extracted_id=point.payload.get("extracted_id"),
                    metadata=point.payload,
                )
                for point in search_result.points
            ]

            logger.info(
                "compound_search_completed",
                results_count=len(results),
                limit=limit,
            )
            return results

    async def get_compound_collection_info(self) -> dict:
        """Return basic stats about the compound collection."""
        client = await self._get_client()

        try:
            info = await client.get_collection(collection_name=self.collection_name)
        except Exception as e:
            logger.exception(
                "failed_to_get_compound_collection_info",
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
                "vector_size": self.VECTOR_SIZE,
            }

    async def close(self) -> None:
        """Close the Qdrant client connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("compound_qdrant_client_closed")
