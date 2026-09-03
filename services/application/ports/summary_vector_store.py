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
        workspace_id: UUID | None = None,
        tags: list[str] | None = None,
        entity_types: list[str] | None = None,
        artifact_tags: list[str] | None = None,
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
        workspace_id: UUID | None = None,
        tags: list[str] | None = None,
        entity_types: list[str] | None = None,
        artifact_tags: list[str] | None = None,
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
        allowed_artifact_ids: list[UUID] | None = None,
        workspace_id: UUID | None = None,
        tags: list[str] | None = None,
        entity_types: list[str] | None = None,
        tag_match_mode: Literal["any", "all"] = "any",
    ) -> list[SummarySearchResult]:
        """Search summary embeddings by dense vector similarity.

        Args:
            query_embedding: Query vector.
            limit: Max results to return.
            entity_type_filter: Restrict to "page" or "artifact" summaries.
            artifact_id_filter: Restrict to a specific artifact.
            score_threshold: Minimum cosine similarity (0.0-1.0).
            allowed_artifact_ids: Optional whitelist of accessible artifact IDs.
            workspace_id: Optional workspace scope for multi-tenant filtering.
            tags: Optional tag filter (case-insensitive).
            entity_types: Optional NER entity type filter.
            tag_match_mode: 'any' = match ANY tag, 'all' = must have ALL tags.

        Returns:
            List of SummarySearchResult ordered by score descending.

        """
        ...

    async def set_summary_payload(
        self,
        entity_type: Literal["page", "artifact"],
        entity_id: UUID,
        payload: dict,
    ) -> None:
        """Patch payload fields on a summary point.

        Used to update metadata (e.g. tags) without re-embedding.
        """
        ...

    async def set_artifact_pages_payload(
        self,
        artifact_id: UUID,
        payload: dict,
    ) -> None:
        """Patch payload on all summary points (page + artifact) belonging to an artifact.

        Used to update artifact-level metadata across all related summary points.
        """
        ...

    async def get_collection_info(self) -> dict:
        """Return collection stats (point count, vector size, etc.)."""
        ...
