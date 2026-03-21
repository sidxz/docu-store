"""Internal models for the chat agent pipeline.

These are NOT DTOs — they never cross application boundaries.
They are internal state passed between agent nodes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class QuestionAnalysis(BaseModel):
    """Output of the question analysis node."""

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
