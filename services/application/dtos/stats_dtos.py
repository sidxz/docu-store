from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WorkflowTypeStats(BaseModel):
    workflow_type: str
    count: int
    avg_duration_seconds: float
    min_duration_seconds: float
    max_duration_seconds: float
    p95_duration_seconds: float


class ActiveWorkflow(BaseModel):
    workflow_type: str
    count: int


class FailedWorkflow(BaseModel):
    workflow_id: str
    workflow_type: str
    started_at: datetime | None
    closed_at: datetime | None
    failure_message: str | None


class WorkflowStatsResponse(BaseModel):
    completed: list[WorkflowTypeStats]
    active: list[ActiveWorkflow]
    recent_failures: list[FailedWorkflow]


class PipelineStatsResponse(BaseModel):
    total_artifacts: int
    total_pages: int
    pages_with_text: int
    pages_with_summary: int
    pages_with_compounds: int
    pages_with_tags: int


class CollectionStats(BaseModel):
    collection_name: str
    points_count: int
    indexed_vectors_count: int
    status: str


class VectorStatsResponse(BaseModel):
    collections: list[CollectionStats]
    embedding_model: dict
    reranker: dict | None


# --- Analytics Aggregation DTOs ---


class TokenUsageBucket(BaseModel):
    """Token usage aggregated by time bucket."""

    date: str  # ISO date string (YYYY-MM-DD)
    mode: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    message_count: int


class TokenUsageStatsResponse(BaseModel):
    buckets: list[TokenUsageBucket]
    total_tokens: int
    total_messages: int


class StepLatencyStats(BaseModel):
    """Latency stats for a single pipeline step."""

    step_name: str
    count: int
    avg_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float


class ChatLatencyStatsResponse(BaseModel):
    steps: list[StepLatencyStats]
    overall_avg_ms: float
    overall_p95_ms: float


class SearchQualityStats(BaseModel):
    """Search quality metrics."""

    search_mode: str
    total_searches: int
    zero_result_count: int
    zero_result_rate: float
    avg_result_count: float


class SearchQualityStatsResponse(BaseModel):
    modes: list[SearchQualityStats]
    total_searches: int
    overall_zero_result_rate: float


class GroundingBucket(BaseModel):
    """Grounding score distribution bucket."""

    mode: str
    total_messages: int
    grounded_count: int
    not_grounded_count: int
    grounded_rate: float
    avg_confidence: float


class GroundingStatsResponse(BaseModel):
    modes: list[GroundingBucket]
    overall_grounded_rate: float
    overall_avg_confidence: float


# --- Knowledge Gaps ---


class KnowledgeGapEntry(BaseModel):
    """An entity detected in chat queries that the corpus couldn't answer."""

    entity_text: str
    entity_type: str
    query_count: int  # Total times this entity appeared in queries
    gap_count: int  # Times it appeared in un-grounded / zero-source answers
    gap_rate: float  # gap_count / query_count


class KnowledgeGapsResponse(BaseModel):
    gaps: list[KnowledgeGapEntry]
    total_unique_entities: int
    total_gap_entities: int


# --- Citation Frequency ---


class CitedArtifactEntry(BaseModel):
    """A document and how often it appears in chat citations."""

    artifact_id: str
    artifact_title: str | None
    citation_count: int
    unique_conversation_count: int


class UncitedArtifactEntry(BaseModel):
    """A document that has never been cited in chat answers."""

    artifact_id: str
    artifact_title: str | None


class CitationFrequencyResponse(BaseModel):
    most_cited: list[CitedArtifactEntry]
    least_cited: list[CitedArtifactEntry]
    never_cited: list[UncitedArtifactEntry]
    never_cited_count: int
    total_artifacts: int
