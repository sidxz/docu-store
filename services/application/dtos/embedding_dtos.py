from uuid import UUID

from pydantic import BaseModel, Field


class GenerateEmbeddingRequest(BaseModel):
    """Request to generate an embedding for a page."""

    page_id: UUID
    text_content: str
    force_regenerate: bool = Field(
        default=False,
        description="If True, regenerate even if embedding already exists",
    )


class EmbeddingDTO(BaseModel):
    """Data transfer object for embedding information."""

    embedding_id: UUID
    page_id: UUID
    artifact_id: UUID
    model_name: str
    dimensions: int
    generated_at: str  # ISO format datetime


class SearchRequest(BaseModel):
    """Request to search for similar pages."""

    query_text: str
    limit: int = Field(default=10, ge=1, le=100)
    artifact_id: UUID | None = Field(
        default=None,
        description="Optional filter to search within specific artifact",
    )
    score_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score (0.0 to 1.0)",
    )


class SearchResultDTO(BaseModel):
    """Data transfer object for search results."""

    page_id: UUID
    artifact_id: UUID
    page_index: int
    similarity_score: float
    text_preview: str | None = Field(
        default=None,
        description="Preview of the page text (if available from read model)",
    )
    artifact_name: str | None = Field(
        default=None,
        description="Name of the artifact (if available from read model)",
    )


class SearchResponse(BaseModel):
    """Response containing search results."""

    query: str
    results: list[SearchResultDTO]
    total_results: int
    model_used: str
