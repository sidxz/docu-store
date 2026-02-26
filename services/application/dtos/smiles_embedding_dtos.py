from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class SmilesEmbeddingDTO(BaseModel):
    """Result returned by EmbedCompoundSmilesUseCase."""

    page_id: UUID
    artifact_id: UUID
    embedded_count: int
    skipped_count: int
    model_name: str


class CompoundSearchRequest(BaseModel):
    """Request to search for structurally similar compounds by SMILES."""

    query_smiles: str = Field(..., description="Query SMILES string (will be canonicalized)")
    limit: int = Field(default=10, ge=1, le=100)
    artifact_id: UUID | None = Field(
        default=None,
        description="Optional filter to search within a specific artifact",
    )
    score_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity score (0.0 to 1.0)",
    )


class CompoundSearchResultDTO(BaseModel):
    """A single compound similarity search result."""

    smiles: str
    canonical_smiles: str | None = None
    extracted_id: str | None = Field(
        default=None,
        description="Label/ID as extracted from the source document",
    )
    confidence: float | None = None
    similarity_score: float
    page_id: UUID
    page_index: int
    artifact_id: UUID
    artifact_name: str | None = None


class CompoundSearchResponse(BaseModel):
    """Response containing compound similarity search results."""

    query_smiles: str
    query_canonical_smiles: str | None = None
    results: list[CompoundSearchResultDTO]
    total_results: int
    model_used: str
