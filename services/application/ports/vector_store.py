from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol
from uuid import UUID

from domain.value_objects.text_embedding import TextEmbedding

if TYPE_CHECKING:
    from application.ports.sparse_embedding_generator import SparseEmbedding


class PageSearchResult:
    """Result from a vector similarity search."""

    def __init__(
        self,
        page_id: UUID,
        artifact_id: UUID,
        score: float,
        page_index: int,
        metadata: dict | None = None,
    ) -> None:
        self.page_id = page_id
        self.artifact_id = artifact_id
        self.score = score
        self.page_index = page_index
        self.metadata = metadata or {}


class VectorStore(Protocol):
    """Port for vector similarity search operations.

    This is a protocol (interface) that abstracts the vector store,
    allowing us to swap between Qdrant, Weaviate, pgvector, etc.
    without changing the application layer.

    Following the Ports & Adapters pattern from Clean Architecture.
    """

    async def ensure_collection_exists(self) -> None:
        """Ensure the vector collection exists with proper schema.

        Should be idempotent - safe to call multiple times.
        """
        ...

    async def upsert_page_embedding(
        self,
        page_id: UUID,
        artifact_id: UUID,
        embedding: TextEmbedding,
        page_index: int,
        metadata: dict | None = None,
    ) -> None:
        """Store or update a page embedding in the vector store.

        Args:
            page_id: The unique ID of the page
            artifact_id: The ID of the artifact this page belongs to
            embedding: The text embedding to store
            page_index: The index/position of this page in the artifact
            metadata: Optional additional metadata to store

        The vector store should use page_id as the primary key,
        so calling this multiple times with the same page_id will update.

        """
        ...

    async def delete_page_embedding(self, page_id: UUID) -> None:
        """Delete a page embedding from the vector store.

        Args:
            page_id: The ID of the page to delete

        Should be idempotent - no error if page doesn't exist.
        Also deletes any chunk-level embeddings for this page.

        """
        ...

    async def upsert_page_chunk_embeddings(
        self,
        page_id: UUID,
        artifact_id: UUID,
        embeddings: list[TextEmbedding],
        page_index: int,
        chunk_count: int,
        metadata: dict | None = None,
        sparse_embeddings: list[SparseEmbedding] | None = None,
        chunk_metadata: list[dict] | None = None,
    ) -> None:
        """Store embeddings for multiple chunks of a single page.

        Replaces any existing chunk embeddings for this page.
        Each chunk is stored as a separate point, keyed by
        (page_id, chunk_index).

        Args:
            page_id: The unique ID of the page
            artifact_id: The ID of the artifact this page belongs to
            embeddings: List of embeddings, one per chunk (ordered by chunk index)
            page_index: The index/position of this page in the artifact
            chunk_count: Total number of chunks for this page
            metadata: Optional additional metadata to store

        """
        ...

    async def search_similar_pages(
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
        """Find pages similar to the query embedding.

        Args:
            query_embedding: The embedding to search for
            limit: Maximum number of results to return
            artifact_id_filter: Optional filter to search within a specific artifact
            score_threshold: Optional minimum similarity score (0.0 to 1.0)
            allowed_artifact_ids: Optional whitelist of accessible artifact IDs
            workspace_id: Optional workspace scope for multi-tenant filtering
            tags: Optional tag filter (case-insensitive)
            entity_types: Optional NER entity type filter
            tag_match_mode: 'any' = match ANY tag, 'all' = must have ALL tags

        Returns:
            List of PageSearchResult, ordered by similarity (highest first)

        """
        ...

    async def search_pages_grouped(
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
        block_types: list[str] | None = None,
        section: str | None = None,
        is_table: bool | None = None,
        is_figure: bool | None = None,
        group_size: int = 1,
    ) -> list[PageSearchResult]:
        """Find pages with server-side dedup by page_id.

        Returns the best-scoring chunk per page using Qdrant group_by.
        Same args as search_similar_pages plus group_size.
        """
        ...

    async def search_hybrid_grouped(
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
        block_types: list[str] | None = None,
        section: str | None = None,
        is_table: bool | None = None,
        is_figure: bool | None = None,
        group_size: int = 1,
    ) -> list[PageSearchResult]:
        """Hybrid search (dense + sparse RRF) with server-side dedup by page_id."""
        ...

    async def set_page_payload(
        self,
        page_id: UUID,
        payload: dict,
    ) -> None:
        """Patch payload fields on all points for a given page.

        Used to update metadata (e.g. tags) without re-embedding.

        Args:
            page_id: The page whose points should be updated
            payload: Payload fields to set/overwrite

        """
        ...

    async def set_artifact_payload(
        self,
        artifact_id: UUID,
        payload: dict,
    ) -> None:
        """Patch payload fields on ALL points for a given artifact.

        Used to update artifact-level metadata (e.g. aggregated tags, authors)
        without re-embedding.

        Args:
            artifact_id: The artifact whose points should be updated
            payload: Payload fields to set/overwrite

        """
        ...

    async def get_collection_info(self) -> dict:
        """Get information about the vector collection.

        Returns:
            Dictionary with stats like vector count, dimensions, etc.

        """
        ...
