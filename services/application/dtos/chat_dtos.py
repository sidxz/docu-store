"""DTOs for the agentic RAG chat system."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# --- Agent Events (streaming) ---


class AgentEvent(BaseModel):
    """Discriminated union for SSE streaming events from the chat agent."""

    type: Literal[
        "step_started",
        "step_completed",
        "retrieval_results",
        "token",
        "structured_block",
        "grounding_result",
        "query_context",
        "done",
        "error",
    ]
    step: str | None = None
    status: Literal["started", "completed", "failed"] | None = None
    description: str | None = None
    output: str | None = None
    thinking_content: str | None = None  # LLM intermediate reasoning (for agent trace)
    thinking_label: str | None = None  # Human-readable label for thinking block
    delta: str | None = None
    sources: list[SourceCitationDTO] | None = None
    block: ContentBlockDTO | None = None
    message_id: UUID | None = None
    total_tokens: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    duration_ms: int | None = None
    error_message: str | None = None
    # Grounding verification result (emitted as grounding_result event)
    grounding_is_grounded: bool | None = None
    grounding_confidence: float | None = None
    # Query context (emitted as query_context event)
    query_context_entities: list[dict] | None = None
    query_context_authors: list[str] | None = None
    query_context_type: str | None = None
    query_context_reformulated: str | None = None
    # SMILES detection + resolution (emitted with query_context event)
    query_context_smiles: list[str] | None = None  # canonical SMILES detected
    query_context_smiles_resolved: list[dict] | None = (
        None  # [{canonical_smiles, extracted_ids, mode}]
    )


# --- Source Citations ---


class SourceCitationDTO(BaseModel):
    """A grounding citation linking a claim to a source passage."""

    artifact_id: UUID
    artifact_title: str | None = None
    authors: list[str] = Field(default_factory=list)
    presentation_date: str | None = None
    page_id: UUID | None = None
    page_index: int | None = None
    page_name: str | None = None
    text_excerpt: str | None = None
    similarity_score: float | None = None
    citation_index: int


# --- Content Blocks ---


class ContentBlockDTO(BaseModel):
    """A typed content block in an assistant message."""

    type: Literal["text", "table", "molecule", "citation_list", "source_card"]
    content: str | None = None
    headers: list[str] | None = None
    rows: list[list[str]] | None = None
    smiles: str | None = None
    label: str | None = None
    sources: list[SourceCitationDTO] | None = None
    page_id: UUID | None = None
    artifact_id: UUID | None = None


# --- Thinking Blocks ---


class QueryContextDTO(BaseModel):
    """Captured query context from the planning stage — persisted on assistant messages."""

    ner_entities: list[dict] = Field(default_factory=list)  # [{entity_text, entity_type}]
    authors: list[str] = Field(default_factory=list)
    query_type: str = ""
    reformulated_query: str = ""
    grounded: bool = False
    smiles_detected: list[str] = Field(default_factory=list)  # canonical SMILES found
    smiles_resolved: list[dict] = Field(
        default_factory=list,
    )  # [{canonical_smiles, extracted_ids, mode}]


class ThinkingBlockDTO(BaseModel):
    """A single labeled thinking block from an LLM call."""

    label: str
    step: str
    content: str


# --- Agent Trace ---


class AgentStepDTO(BaseModel):
    """A single step in the agent execution trace."""

    step: str
    status: Literal["started", "completed", "failed"]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    thinking_content: str | None = None  # LLM intermediate reasoning


class AgentTraceDTO(BaseModel):
    """Full execution trace of the agent pipeline."""

    steps: list[AgentStepDTO] = Field(default_factory=list)
    thinking_blocks: list[ThinkingBlockDTO] = Field(default_factory=list)
    total_duration_ms: int | None = None
    retry_count: int = 0
    grounding_is_grounded: bool | None = None
    grounding_confidence: float | None = None


# --- Token Usage ---


class TokenUsageDTO(BaseModel):
    prompt: int = 0
    completion: int = 0
    total: int = 0


# --- Chat Messages ---


class ChatMessageDTO(BaseModel):
    """A single message in a conversation."""

    conversation_id: UUID
    message_id: UUID
    role: Literal["user", "assistant"]
    content: str
    structured_content: list[ContentBlockDTO] | None = None
    sources: list[SourceCitationDTO] = Field(default_factory=list)
    agent_trace: AgentTraceDTO | None = None
    token_usage: TokenUsageDTO | None = None
    query_context: QueryContextDTO | None = None
    created_at: datetime


# --- Conversations ---


class ConversationDTO(BaseModel):
    """A chat conversation."""

    conversation_id: UUID
    workspace_id: UUID
    owner_id: UUID
    title: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    model_used: str | None = None
    is_archived: bool = False


class ConversationDetailDTO(ConversationDTO):
    """Conversation with its messages."""

    messages: list[ChatMessageDTO] = Field(default_factory=list)


# --- Feedback ---


class ChatFeedbackDTO(BaseModel):
    """User feedback on a chat message."""

    conversation_id: UUID
    message_id: UUID
    workspace_id: UUID
    user_id: UUID
    feedback: Literal["positive", "negative"]
    created_at: datetime
