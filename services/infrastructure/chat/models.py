"""Internal models for the chat agent pipeline.

These are NOT DTOs — they never cross application boundaries.
They are internal state passed between agent nodes.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class QuestionAnalysis(BaseModel):
    """Output of the question analysis node (Quick Mode)."""

    query_type: str  # factual, comparative, exploratory, compound, follow_up
    reformulated_query: str
    entities: list[str] = Field(default_factory=list)
    smiles_detected: list[str] = Field(default_factory=list)
    search_strategy: str  # hierarchical, summary, compound, hybrid
    summary: str


class GroundingResult(BaseModel):
    """Output of the grounding verification node."""

    is_grounded: bool
    confidence: float = Field(ge=0.0, le=1.0)
    supported_claims: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    verification_summary: str


# --- Thinking Mode models ---

# Only these NER entity types are used as Qdrant filters
QUERY_FILTER_ENTITY_TYPES = {"target", "gene_name", "compound_name"}


class NEREntityFilter(BaseModel):
    """A single NER entity to use as a Qdrant filter."""

    entity_text: str
    entity_type: str  # target, gene_name, compound_name


class QueryPlan(BaseModel):
    """Output of the query planning node (Thinking Mode).

    Combines NER extraction + GLiNER2 author detection + LLM planning.
    """

    # From LLM
    query_type: str  # factual, comparative, exploratory, compound, follow_up
    reformulated_query: str
    sub_queries: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    smiles_detected: list[str] = Field(default_factory=list)
    search_strategy: str  # hierarchical, summary, compound, hybrid
    hyde_hypothesis: str | None = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    summary: str

    # From NERExtractorPort (filtered to QUERY_FILTER_ENTITY_TYPES)
    ner_entity_filters: list[NEREntityFilter] = Field(default_factory=list)

    # From StructuredExtractorPort (GLiNER2)
    author_mentions: list[str] = Field(default_factory=list)


class RetrievalResult(BaseModel):
    """A single retrieved source with expanded context (Thinking Mode)."""

    source_type: Literal["chunk", "summary"]
    artifact_id: UUID
    artifact_title: str | None = None
    authors: list[str] = Field(default_factory=list)
    presentation_date: str | None = None
    page_id: UUID | None = None
    page_index: int | None = None
    page_name: str | None = None
    expanded_text: str  # chunk + neighbors, or full summary
    matched_text: str  # original matched chunk (for highlighting / citation excerpt)
    similarity_score: float
    rerank_score: float | None = None
    query_source: str = "primary"  # primary, sub_query_0, sub_query_1, hyde


class ContextMetadata(BaseModel):
    """Metadata about the assembled context (Thinking Mode).

    Feeds into Stage 4 for prompt adaptation.
    """

    total_sources: int
    high_relevance_count: int
    avg_relevance_score: float
    unique_artifacts: int
    has_summaries: bool
