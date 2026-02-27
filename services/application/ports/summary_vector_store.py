"""Port for summary embedding storage and search."""

from typing import Literal, Protocol
from uuid import UUID

from domain.value_objects.text_embedding import TextEmbedding


class SummarySearchResult:
    """Result from a summary similarity search."""

    def __init__(
        self,
        point_id: str,
        entity_type: Literal["page", "artifact"],
        entity_id: UUID,
        artifact_id: UUID,
        score: float,
        summary_text: str | None = None,
        artifact_title: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self.point_id = point_id
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.artifact_id = artifact_id
        self.score = score
        self.summary_text = summary_text
        self.artifact_title = artifact_title
        self.metadata = metadata or {}


class SummaryVectorStore(Protocol):
    """Port for storing and searching summary embeddings.

    A unified collection for both page-level and artifact-level summaries.
    Supports dense vector search (Phase 1) with schema ready for sparse
    vectors (Phase 2).
    """

    async def ensure_collection_exists(self) -> None:
        """Ensure the collection exists with proper schema. Idempotent."""
        ...

    async def upsert_page_summary_embedding(
        self,
        page_id: UUID,
        artifact_id: UUID,
        embedding: TextEmbedding,
        summary_text: str,
        artifact_title: str | None = None,
        page_index: int = 0,
    ) -> None:
        """Store or update a page summary embedding.

        Point ID: ``page-{page_id}`` for deterministic idempotent upserts.
        """
        ...

    async def upsert_artifact_summary_embedding(
        self,
        artifact_id: UUID,
        embedding: TextEmbedding,
        summary_text: str,
        artifact_title: str | None = None,
        page_count: int = 0,
    ) -> None:
        """Store or update an artifact summary embedding.

        Point ID: ``artifact-{artifact_id}`` for deterministic idempotent upserts.
        """
        ...

    async def delete_page_summary(self, page_id: UUID) -> None:
        """Delete the page summary point. Idempotent — no error if missing."""
        ...

    async def delete_artifact_summary(self, artifact_id: UUID) -> None:
        """Delete the artifact summary point. Idempotent — no error if missing."""
        ...

    async def search_summaries(
        self,
        query_embedding: TextEmbedding,
        limit: int = 10,
        entity_type_filter: Literal["page", "artifact"] | None = None,
        artifact_id_filter: UUID | None = None,
        score_threshold: float | None = None,
    ) -> list[SummarySearchResult]:
        """Search summary embeddings by dense vector similarity.

        Args:
            query_embedding: Query vector.
            limit: Max results to return.
            entity_type_filter: Restrict to "page" or "artifact" summaries.
            artifact_id_filter: Restrict to a specific artifact.
            score_threshold: Minimum cosine similarity (0.0–1.0).

        Returns:
            List of SummarySearchResult ordered by score descending.

        """
        ...

    async def get_collection_info(self) -> dict:
        """Return collection stats (point count, vector size, etc.)."""
        ...
