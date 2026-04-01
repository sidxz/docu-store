import re
from uuid import NAMESPACE_URL, UUID, uuid5

import structlog
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.models import Distance, PointStruct, VectorParams

from application.ports.compound_vector_store import CompoundSearchResult, CompoundVectorStore
from domain.value_objects.text_embedding import TextEmbedding

logger = structlog.get_logger()

# Pattern to split compound names at letter/digit boundaries: GSK286 → GSK 286
_LETTER_DIGIT_BOUNDARY = re.compile(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])")


def _compound_name_variants(name: str) -> list[str]:
    """Generate normalised variants of a compound name for fuzzy matching.

    Handles common mismatches between user input and CSER-extracted labels:
    - GSK286 vs GSK-286 vs GSK 286
    - Case differences
    - Leading/trailing whitespace
    """
    name = name.strip()
    if not name:
        return []

    seen: set[str] = set()
    variants: list[str] = []

    def _add(v: str) -> None:
        if v and v not in seen:
            seen.add(v)
            variants.append(v)

    # 1. Original
    _add(name)

    # 2. Case variants
    _add(name.upper())
    _add(name.lower())

    # 3. Strip hyphens / replace with nothing
    no_hyphen = name.replace("-", "").replace(" ", "")
    _add(no_hyphen)
    _add(no_hyphen.upper())

    # 4. Split at letter/digit boundary with hyphen: GSK286 → GSK-286
    hyphenated = _LETTER_DIGIT_BOUNDARY.sub("-", name.replace("-", "").replace(" ", ""))
    _add(hyphenated)
    _add(hyphenated.upper())

    # 5. Split at letter/digit boundary with space: GSK286 → GSK 286
    spaced = _LETTER_DIGIT_BOUNDARY.sub(" ", name.replace("-", "").replace(" ", ""))
    _add(spaced)
    _add(spaced.upper())

    return variants


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

            if not exists:
                await client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.VECTOR_SIZE,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(
                    "compound_collection_created",
                    collection=self.collection_name,
                    vector_size=self.VECTOR_SIZE,
                )

            # Ensure indexes exist (idempotent — safe on existing collections)
            await self._ensure_indexes(client)

        except Exception as e:
            logger.exception(
                "failed_to_create_compound_collection",
                collection=self.collection_name,
                error=str(e),
            )
            raise

    async def _ensure_indexes(self, client: AsyncQdrantClient) -> None:
        """Create payload indexes if they don't already exist. Idempotent."""
        index_fields = [
            "page_id",
            "artifact_id",
            "canonical_smiles",
            "workspace_id",
            "extracted_id",
        ]
        for field in index_fields:
            try:
                await client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                # Index already exists — Qdrant returns an error on duplicates, which is fine
                logger.debug("compound_index_already_exists", field=field)

    async def upsert_compound_embeddings(
        self,
        page_id: UUID,
        artifact_id: UUID,
        page_index: int,
        compounds: list[dict],
        embeddings: list[TextEmbedding],
        workspace_id: UUID | None = None,
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
                "workspace_id": str(workspace_id) if workspace_id else None,
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
        except Exception as e:
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
        allowed_artifact_ids: list[UUID] | None = None,
        workspace_id: UUID | None = None,
    ) -> list[CompoundSearchResult]:
        """Find compounds by SMILES structural similarity."""
        client = await self._get_client()

        must_conditions = []
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

    async def get_compounds_by_extracted_id(
        self,
        extracted_id: str,
        workspace_id: UUID | None = None,
        allowed_artifact_ids: list[UUID] | None = None,
        limit: int = 10,
    ) -> list[CompoundSearchResult]:
        """Find compounds by their extracted document ID (name/label).

        Uses metadata filtering with the extracted_id KEYWORD index.
        Tries multiple normalised variants (with/without hyphens, spaces)
        because CSER labels may differ from user input.
        Returns results with vectors stashed in metadata['_vector'] for
        subsequent similarity search without re-embedding.
        """
        client = await self._get_client()

        # Generate normalised variants to handle common mismatches:
        #   "GSK286" vs "GSK-286" vs "GSK 286" vs "gsk286"
        variants = _compound_name_variants(extracted_id)

        must_conditions = [
            models.FieldCondition(
                key="extracted_id",
                match=models.MatchAny(any=variants),
            ),
        ]
        if workspace_id:
            must_conditions.append(
                models.FieldCondition(
                    key="workspace_id",
                    match=models.MatchValue(value=str(workspace_id)),
                ),
            )
        if allowed_artifact_ids is not None:
            must_conditions.append(
                models.FieldCondition(
                    key="artifact_id",
                    match=models.MatchAny(any=[str(aid) for aid in allowed_artifact_ids]),
                ),
            )

        try:
            scroll_result, _next_offset = await client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(must=must_conditions),
                limit=limit,
                with_payload=True,
                with_vectors=True,
            )
        except Exception as e:
            logger.exception(
                "compound_lookup_by_name_failed",
                extracted_id=extracted_id,
                error=str(e),
            )
            raise

        # Deduplicate by canonical_smiles — same compound can appear on multiple pages
        seen_canonical: set[str] = set()
        results: list[CompoundSearchResult] = []

        for point in scroll_result:
            canonical = point.payload.get("canonical_smiles") or point.payload.get("smiles", "")
            if canonical in seen_canonical:
                continue
            seen_canonical.add(canonical)

            # Stash the vector in metadata so callers can reuse it for similarity search
            metadata = dict(point.payload)
            if point.vector is not None:
                metadata["_vector"] = point.vector

            results.append(
                CompoundSearchResult(
                    page_id=UUID(point.payload["page_id"]),
                    artifact_id=UUID(point.payload["artifact_id"]),
                    score=1.0,  # exact metadata match
                    page_index=point.payload["page_index"],
                    smiles=point.payload["smiles"],
                    canonical_smiles=point.payload.get("canonical_smiles"),
                    extracted_id=point.payload.get("extracted_id"),
                    metadata=metadata,
                ),
            )

        logger.info(
            "compound_lookup_by_name_completed",
            extracted_id=extracted_id,
            raw_matches=len(scroll_result),
            unique_structures=len(results),
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
                "indexed_vectors_count": info.indexed_vectors_count,
                "points_count": info.points_count,
                "status": str(info.status),
                "vector_size": self.VECTOR_SIZE,
            }

    async def close(self) -> None:
        """Close the Qdrant client connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("compound_qdrant_client_closed")
