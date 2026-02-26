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
        description="Name/filename of the artifact (if available from read model)",
    )
    artifact_details: "ArtifactDetailsDTO | None" = Field(
        default=None,
        description="Full artifact details including metadata, pages, and tags",
    )


class ArtifactDetailsDTO(BaseModel):
    """Detailed artifact information for search results."""

    artifact_id: UUID = Field(..., description="Unique identifier of the artifact")
    source_uri: str | None = Field(None, description="URI pointing to the source of the artifact")
    source_filename: str | None = Field(None, description="Original filename of the artifact")
    artifact_type: str = Field(..., description="Classification type of the artifact")
    mime_type: str = Field(..., description="MIME type of the artifact")
    storage_location: str = Field(..., description="Location where the artifact is stored")
    page_count: int = Field(
        default=0,
        description="Number of pages in the artifact",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="List of tags associated with the artifact",
    )
    summary: str | None = Field(
        None,
        description="Summary candidate extracted from the artifact",
    )
    title: str | None = Field(
        None,
        description="Title mention extracted from the artifact",
    )


class SearchResponse(BaseModel):
    """Response containing search results."""

    query: str
    results: list[SearchResultDTO]
    total_results: int
    model_used: str


# Forward reference resolution
SearchResultDTO.model_rebuild()
