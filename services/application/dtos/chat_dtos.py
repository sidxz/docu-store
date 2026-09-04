"""DTOs for the agentic RAG chat system."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from application.dtos.compound_dtos import BioactivityDTO
from domain.value_objects.chat_surface import ChatSurface

# --- Agent Events (streaming) ---


class AgentEvent(BaseModel):
    """Discriminated union for SSE streaming events from the chat agent."""

    type: Literal[
        "step_started",
        "step_completed",
        "retrieval_results",
        "literature_results",
        "token",
        "reasoning_token",
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
    model: str | None = None  # what actually answered, as the provider named it
    duration_ms: int | None = None
    error_message: str | None = None
    # Grounding verification result (emitted as grounding_result event)
    grounding_is_grounded: bool | None = None
    grounding_confidence: float | None = None
    # Papers found by search_literature (emitted as literature_results event).
    # Carried whole rather than as citations: the cards need the licence and the
    # ingest verdict, which a citation has no business holding.
    literature_results: list[dict] | None = None
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
    # "document" cites a page in this corpus; "literature" cites a paper the
    # agent has only ever seen the abstract of. The client renders the two
    # differently on purpose -- an abstract-derived claim should not look as
    # grounded as one read off a page.
    source_type: str = "document"
    external_url: str | None = None


# --- Content Blocks ---


class ChartSeriesDTO(BaseModel):
    """One line, bar group or point cloud. ``points`` are (x, y) pairs.

    x is a year for the time panels and a category index for the categorical
    ones, so a single shape covers every panel and the renderer needs one
    switch rather than six.
    """

    name: str
    points: list[tuple[float, float]]
    labels: list[str] | None = None
    """One label per point, index-parallel to ``points``. Set when a point is an
    identifiable thing -- a paper -- rather than a bucket, so the tooltip can
    name it. A parallel array rather than a third tuple slot: ``points`` is
    shared by every panel and mirrored in TS, and widening it breaks both
    renderer paths."""


class ChartSpecDTO(BaseModel):
    """A chart the tool computed. No value here originates in model output."""

    panel: Literal["timeline", "evidence_mix", "landmarks", "stance"]
    title: str
    x_label: str
    y_label: str
    series: list[ChartSeriesDTO]
    categories: list[str] | None = None
    """Tick labels when x is a category index rather than a year."""
    partial_x: float | None = None
    """The x value that is incomplete -- the current year. Rendered hatched;
    without it every chart ends on a false decline."""
    footnote: str | None = None
    notes: list[str] | None = None
    """Per-item annotations shown under the chart. Stance uses it for the
    fragment of the abstract that decided each verdict, so a reader can
    overrule the classifier instead of taking the bars on trust."""
    source_query: str | None = None
    """The Europe PMC query these counts came from, so a reader can check that
    the chart and the cards describe the same population."""


class ContentBlockDTO(BaseModel):
    """A typed content block in an assistant message."""

    type: Literal["text", "table", "molecule", "citation_list", "source_card", "chart"]
    content: str | None = None
    headers: list[str] | None = None
    rows: list[list[str]] | None = None
    smiles: str | None = None
    label: str | None = None
    sources: list[SourceCitationDTO] | None = None
    page_id: UUID | None = None
    artifact_id: UUID | None = None
    bioactivities: list[BioactivityDTO] | None = None
    chart: ChartSpecDTO | None = None


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
    reasoning_content: str | None = None  # model native chain-of-thought (thinking modes)
    total_duration_ms: int | None = None
    retry_count: int = 0
    grounding_is_grounded: bool | None = None
    grounding_confidence: float | None = None


# --- Token Usage ---


class TokenUsageDTO(BaseModel):
    prompt: int = 0
    completion: int = 0
    total: int = 0
    # The model the provider reported answering with — the resolved name, so an
    # OpenRouter route names the id it served. Comma-joined if a turn used more
    # than one. None on messages written before this was recorded.
    model: str | None = None


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
    # Papers the literature searches returned this turn. Persisted with the
    # message because the panel is rebuilt from it when a conversation is
    # reopened -- a citation whose panel is empty leads nowhere.
    literature_results: list[dict] | None = None
    created_at: datetime


# --- Conversations ---


class ConversationDTO(BaseModel):
    """A chat conversation."""

    conversation_id: UUID
    workspace_id: UUID
    owner_id: UUID
    title: str | None = None
    folder_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    model_used: str | None = None
    is_archived: bool = False
    # Conversations created before surfaces existed have no value stored and
    # read back as RESEARCH, which is where they were in fact created.
    surface: ChatSurface = ChatSurface.RESEARCH


class ConversationDetailDTO(ConversationDTO):
    """Conversation with its messages."""

    messages: list[ChatMessageDTO] = Field(default_factory=list)
    active_run: bool = False


class EntityRefDTO(BaseModel):
    """A named entity discussed in a conversation (for recent-chat chips)."""

    text: str
    type: str


class CitedDocumentDTO(BaseModel):
    """A document cited in a conversation (fallback chip)."""

    artifact_id: UUID
    title: str | None = None


class RecentConversationDTO(ConversationDTO):
    """A conversation enriched with a summary for the dashboard recent-chats panel."""

    last_answer_snippet: str | None = None
    entities: list[EntityRefDTO] = Field(default_factory=list)
    cited_documents: list[CitedDocumentDTO] = Field(default_factory=list)
    source_count: int = 0
    grounded: bool | None = None
    grounded_confidence: float | None = None


# --- Folders ---


class ChatFolderDTO(BaseModel):
    """A per-user chat folder within a workspace (flat, non-nested)."""

    folder_id: UUID
    workspace_id: UUID
    owner_id: UUID
    name: str
    created_at: datetime
    updated_at: datetime
    chat_count: int = 0


# --- Feedback ---


class ChatFeedbackDTO(BaseModel):
    """User feedback on a chat message."""

    conversation_id: UUID
    message_id: UUID
    workspace_id: UUID
    user_id: UUID
    feedback: Literal["positive", "negative"]
    created_at: datetime
