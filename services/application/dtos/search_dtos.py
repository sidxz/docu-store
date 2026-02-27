"""DTOs for summary search endpoints."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SummarySearchRequest(BaseModel):
    """Request to search page/artifact summaries by semantic similarity."""

    query_text: str = Field(..., min_length=1)
    limit: int = Field(default=10, ge=1, le=100)
    entity_type: Literal["page", "artifact"] | None = Field(
        default=None,
        description="Restrict to page or artifact summaries. None = both.",
    )
    artifact_id: UUID | None = Field(
        default=None,
        description="Restrict search to a specific artifact.",
    )
    score_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity score.",
    )


class SummarySearchResultDTO(BaseModel):
    """A single hit from the summary embedding collection."""

    entity_type: Literal["page", "artifact"]
    entity_id: UUID
    artifact_id: UUID
    similarity_score: float
    summary_text: str | None = None
    artifact_title: str | None = None
    metadata: dict = Field(default_factory=dict)


class SummarySearchResponse(BaseModel):
    """Response from summary search."""

    query: str
    results: list[SummarySearchResultDTO]
    total_results: int
    model_used: str


class HierarchicalSearchRequest(BaseModel):
    """Request for hierarchical cross-collection search.

    Searches both raw text chunks (page_embeddings) and summaries
    (summary_embeddings), then merges and re-ranks the results.
    """

    query_text: str = Field(..., min_length=1)
    limit: int = Field(default=10, ge=1, le=50)
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    include_chunks: bool = Field(
        default=True,
        description="Whether to include raw chunk hits alongside summary hits.",
    )


class ChunkHit(BaseModel):
    """A matching raw text chunk from page_embeddings."""

    page_id: UUID
    artifact_id: UUID
    page_index: int
    score: float
    text_preview: str | None = None


class SummaryHit(BaseModel):
    """A matching summary from summary_embeddings."""

    entity_type: Literal["page", "artifact"]
    entity_id: UUID
    artifact_id: UUID
    score: float
    summary_text: str | None = None
    artifact_title: str | None = None


class HierarchicalSearchResponse(BaseModel):
    """Hierarchical search result grouping summaries with supporting chunks."""

    query: str
    summary_hits: list[SummaryHit]
    chunk_hits: list[ChunkHit]
    total_summary_hits: int
    total_chunk_hits: int
    model_used: str
