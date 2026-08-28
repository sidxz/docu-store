"""Use cases for the agentic RAG chat system."""

from __future__ import annotations

import asyncio
import contextlib
import re
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4

import structlog
from returns.result import Failure, Result, Success

from application.dtos.chat_dtos import (
    AgentEvent,
    AgentStepDTO,
    AgentTraceDTO,
    ChatFeedbackDTO,
    ChatMessageDTO,
    CitedDocumentDTO,
    ContentBlockDTO,
    ConversationDetailDTO,
    ConversationDTO,
    EntityRefDTO,
    QueryContextDTO,
    RecentConversationDTO,
    SourceCitationDTO,
    ThinkingBlockDTO,
    TokenUsageDTO,
)
from application.dtos.errors import AppError
from application.dtos.usage_dtos import MonthUsage, TokenUsageEvent, UserTokenUsageResponse
from application.ports.token_limit_store import TokenLimitStore
from application.ports.token_usage_store import TokenUsageStore
from application.use_cases.token_limit_use_cases import (
    effective_limit,
    month_total,
    month_usage_by_kind,
)
from infrastructure.llm.token_counter import TokenCounter

if TYPE_CHECKING:
    from application.ports.chat_agent import ChatAgentPort
    from application.ports.chat_repository import ChatRepository

log = structlog.get_logger(__name__)


class CreateConversationUseCase:
    """Create a new chat conversation."""

    def __init__(self, chat_repository: ChatRepository) -> None:
        self._repo = chat_repository

    async def execute(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        title: str | None = None,
    ) -> Result[ConversationDTO, AppError]:
        try:
            now = datetime.now(UTC)
            conversation = ConversationDTO(
                conversation_id=uuid4(),
                workspace_id=workspace_id,
                owner_id=owner_id,
                title=title,
                created_at=now,
                updated_at=now,
            )
            created = await self._repo.create_conversation(conversation)
            log.info("chat.conversation.created", id=str(created.conversation_id))
            return Success(created)
        except Exception as e:
            log.exception("chat.conversation.create_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to create conversation: {e!s}"))


class ListConversationsUseCase:
    """List conversations for a user in a workspace."""

    def __init__(self, chat_repository: ChatRepository) -> None:
        self._repo = chat_repository

    async def execute(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        skip: int = 0,
        limit: int = 20,
        is_archived: bool = False,
        folder_id: UUID | None = None,
    ) -> Result[list[ConversationDTO], AppError]:
        try:
            conversations = await self._repo.list_conversations(
                workspace_id=workspace_id,
                owner_id=owner_id,
                skip=skip,
                limit=limit,
                is_archived=is_archived,
                folder_id=folder_id,
            )
            return Success(conversations)
        except Exception as e:
            log.exception("chat.conversations.list_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to list conversations: {e!s}"))


# link pattern BEFORE the single-char class, else "[" strips first and leaves "(url)"
_MD_STRIP = re.compile(r"(\$[^$]*\$|!?\[[^\]]*\]\([^)]*\)|[*#`_>\[\]])")


def _plain_text(text: str) -> str:
    return re.sub(r"\s+", " ", _MD_STRIP.sub("", text)).strip()


def _build_recent_summary(
    conv: ConversationDTO, messages: list[ChatMessageDTO]
) -> RecentConversationDTO:
    assistant = [m for m in messages if m.role == "assistant"]
    last = assistant[-1] if assistant else None
    snippet = _plain_text(last.content)[:120] if last and last.content else None

    order: list[tuple[str, str]] = []  # (lower_text, ...) preserves first-seen order
    counts: dict[str, int] = {}
    labels: dict[str, tuple[str, str]] = {}  # lower -> (text, type)

    def add(text, etype):
        if not text:
            return
        key = text.lower()
        if key not in labels:
            labels[key] = (text, etype or "other")
            order.append((key, etype or "other"))
        counts[key] = counts.get(key, 0) + 1

    for m in messages:
        qc = m.query_context
        if not qc:
            continue
        for e in qc.ner_entities:
            add(e.get("entity_text"), e.get("entity_type"))
        for sr in qc.smiles_resolved:
            for cid in sr.get("extracted_ids", []):
                add(cid, "compound")

    _PRI = {"compound": 0, "compound_name": 0, "target": 1, "gene": 1, "assay": 2}
    ranked = sorted(order, key=lambda o: (_PRI.get(o[1], 9), -counts[o[0]]))
    entities = [EntityRefDTO(text=labels[k][0], type=labels[k][1]) for k, _ in ranked[:4]]

    seen_art: dict = {}
    for m in messages:
        for s in m.sources:
            seen_art.setdefault(s.artifact_id, s.artifact_title)
    cited = [CitedDocumentDTO(artifact_id=a, title=t) for a, t in list(seen_art.items())[:2]]

    trace = last.agent_trace if last else None
    return RecentConversationDTO(
        **conv.model_dump(),
        last_answer_snippet=snippet,
        entities=entities,
        cited_documents=cited,
        source_count=len(seen_art),
        grounded=(trace.grounding_is_grounded if trace else None),
        grounded_confidence=(trace.grounding_confidence if trace else None),
    )


class ListRecentConversationsUseCase:
    """Top-N recent conversations enriched with a UI summary."""

    def __init__(self, chat_repository: ChatRepository) -> None:
        self._repo = chat_repository

    async def execute(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        limit: int = 5,
    ) -> Result[list[RecentConversationDTO], AppError]:
        try:
            convs = await self._repo.list_recent_conversations(
                workspace_id=workspace_id,
                owner_id=owner_id,
                limit=limit,
            )
            out = []
            for conv in convs:
                messages = await self._repo.get_messages(conv.conversation_id)
                out.append(_build_recent_summary(conv, messages))
            return Success(out)
        except Exception as e:
            log.exception("chat.recent.list_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to list recent chats: {e!s}"))


class GetUserTokenUsageUseCase:
    """Per-user token totals from the usage ledger + current-month block with limit."""

    def __init__(
        self,
        token_usage_store: TokenUsageStore,
        token_limit_store: TokenLimitStore,
    ) -> None:
        self._usage = token_usage_store
        self._limits = token_limit_store

    async def _limit_or_none(self, workspace_id: UUID, owner_id: UUID) -> int | None:
        """Limits are display garnish here — a broken limits read must not 500 the ledger totals."""
        try:
            return await effective_limit(self._limits, workspace_id, owner_id)
        except Exception as e:
            log.warning("chat.usage.limit_read_failed", error=str(e))
            return None

    async def execute(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        days: int | None = None,
        kind: str | None = None,
        exempt: bool = False,
    ) -> Result[UserTokenUsageResponse, AppError]:
        try:
            since = datetime.now(UTC) - timedelta(days=days) if days else None
            usage, by_kind, limit = await asyncio.gather(
                self._usage.sum_for_user(workspace_id, owner_id, since=since, kind=kind),
                month_usage_by_kind(self._usage, workspace_id, owner_id),
                self._limit_or_none(workspace_id, owner_id),
            )
            return Success(
                UserTokenUsageResponse(
                    prompt=usage.prompt,
                    completion=usage.completion,
                    total=usage.total,
                    month=MonthUsage(
                        chat=by_kind.get("chat", TokenUsageDTO()).total,
                        ingestion=by_kind.get("ingestion", TokenUsageDTO()).total,
                        total=month_total(by_kind),
                        # Exempt (admin) callers are never enforced — don't render a limit.
                        limit=None if exempt else limit,
                    ),
                ),
            )
        except Exception as e:
            log.exception("chat.usage.get_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to get token usage: {e!s}"))


class GetConversationUseCase:
    """Get a conversation with its messages."""

    def __init__(self, chat_repository: ChatRepository) -> None:
        self._repo = chat_repository

    async def execute(
        self,
        conversation_id: UUID,
        workspace_id: UUID | None = None,
        owner_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Result[ConversationDetailDTO, AppError]:
        try:
            conversation = await self._repo.get_conversation(
                conversation_id,
                workspace_id=workspace_id,
                owner_id=owner_id,
            )
            if conversation is None:
                return Failure(AppError("not_found", "Conversation not found"))

            messages = await self._repo.get_messages(
                conversation_id,
                skip=skip,
                limit=limit,
            )
            return Success(
                ConversationDetailDTO(
                    **conversation.model_dump(),
                    messages=messages,
                ),
            )
        except Exception as e:
            log.exception("chat.conversation.get_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to get conversation: {e!s}"))


class DeleteConversationUseCase:
    """Delete a conversation and all its messages."""

    def __init__(self, chat_repository: ChatRepository) -> None:
        self._repo = chat_repository

    async def execute(
        self,
        conversation_id: UUID,
        workspace_id: UUID | None = None,
        owner_id: UUID | None = None,
    ) -> Result[bool, AppError]:
        try:
            deleted = await self._repo.delete_conversation(
                conversation_id,
                workspace_id=workspace_id,
                owner_id=owner_id,
            )
            if not deleted:
                return Failure(AppError("not_found", "Conversation not found"))
            log.info("chat.conversation.deleted", id=str(conversation_id))
            return Success(True)
        except Exception as e:
            log.exception("chat.conversation.delete_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to delete conversation: {e!s}"))


class SendMessageUseCase:
    """Send a message and stream the agent response.

    This is the main chat entry point. It:
    1. Appends the user message to the conversation
    2. Runs the agent pipeline (streaming events)
    3. Saves the assistant response when complete
    """

    def __init__(
        self,
        chat_repository: ChatRepository,
        chat_agent: ChatAgentPort,
        token_usage_store: TokenUsageStore,
    ) -> None:
        self._repo = chat_repository
        self._agent = chat_agent
        self._usage = token_usage_store

    async def execute(
        self,
        conversation_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        message: str,
        allowed_artifact_ids: list[UUID] | None = None,
        mode: Literal["quick", "thinking", "deep_thinking"] | None = None,
        reasoning: dict[str, str] | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        from infrastructure.llm import reasoning_context

        _reasoning_token = reasoning_context.set_reasoning_override(reasoning)
        try:
            # Verify conversation exists and belongs to the sender
            conversation = await self._repo.get_conversation(
                conversation_id,
                workspace_id=workspace_id,
                owner_id=owner_id,
            )
            if conversation is None:
                yield AgentEvent(type="error", error_message="Conversation not found")
                return

            # Save user message
            now = datetime.now(UTC)
            user_msg = ChatMessageDTO(
                conversation_id=conversation_id,
                message_id=uuid4(),
                role="user",
                content=message,
                created_at=now,
            )
            await self._repo.append_message(user_msg)

            # Auto-title from first message
            if conversation.title is None:
                title = message[:100].strip()
                if len(message) > 100:
                    title += "..."
                await self._repo.update_conversation(
                    conversation_id,
                    title=title,
                )

            # Get conversation history for context
            history = await self._repo.get_recent_messages(conversation_id, limit=10)

            # Extract previous citations from last grounded assistant message
            previous_citations: list[SourceCitationDTO] | None = None
            for msg in reversed(history):
                if (
                    msg.role == "assistant"
                    and msg.sources
                    and msg.query_context is not None
                    and msg.query_context.grounded
                ):
                    previous_citations = msg.sources
                    break

            log.info(
                "chat.send_message.context",
                conversation_id=str(conversation_id),
                history_len=len(history),
                has_previous_citations=previous_citations is not None,
                previous_citation_count=len(previous_citations) if previous_citations else 0,
                mode=mode,
            )

            # Run agent pipeline and stream events, accumulating step trace
            draft_answer = ""
            final_sources: list = []
            final_event: AgentEvent | None = None
            trace_steps: dict[str, AgentStepDTO] = {}
            thinking_blocks: list[ThinkingBlockDTO] = []
            grounding_is_grounded: bool | None = None
            grounding_confidence: float | None = None
            query_context: QueryContextDTO | None = None
            structured_blocks: list[ContentBlockDTO] = []
            reasoning_parts: list[str] = []

            # The counter is ambient for the whole pipeline: every LLM call the
            # agent makes (planning, tool loop, synthesis, formatting) records
            # provider-reported usage here, and Langfuse traces inherit the
            # user/conversation identity.
            counter = TokenCounter(
                user_id=str(owner_id),
                session_id=str(conversation_id),
                workspace_id=str(workspace_id),
                tags=["chat"],
            )
            try:
                with counter:
                    async for event in self._agent.run(
                        message=message,
                        conversation_history=history,
                        workspace_id=workspace_id,
                        allowed_artifact_ids=allowed_artifact_ids,
                        mode=mode,
                        previous_citations=previous_citations,
                    ):
                        if event.type == "token":
                            draft_answer += event.delta or ""
                        elif event.type == "reasoning_token":
                            reasoning_parts.append(event.delta or "")
                        elif event.type == "step_started" and event.step:
                            trace_steps[event.step] = AgentStepDTO(
                                step=event.step,
                                status="started",
                                started_at=datetime.now(UTC),
                                output_summary=event.description,
                            )
                        elif event.type == "step_completed" and event.step:
                            if event.step in trace_steps:
                                s = trace_steps[event.step]
                                if event.status != "started":
                                    s.status = "completed"
                                    s.completed_at = datetime.now(UTC)
                                s.output_summary = event.output
                                if event.thinking_content:
                                    if s.thinking_content:
                                        s.thinking_content += "\n\n---\n\n" + event.thinking_content
                                    else:
                                        s.thinking_content = event.thinking_content
                                    thinking_blocks.append(
                                        ThinkingBlockDTO(
                                            label=event.thinking_label or f"{event.step} thought",
                                            step=event.step or "unknown",
                                            content=event.thinking_content,
                                        ),
                                    )
                        elif event.type == "query_context":
                            query_context = QueryContextDTO(
                                ner_entities=event.query_context_entities or [],
                                authors=event.query_context_authors or [],
                                query_type=event.query_context_type or "",
                                reformulated_query=event.query_context_reformulated or "",
                                smiles_detected=event.query_context_smiles or [],
                                smiles_resolved=event.query_context_smiles_resolved or [],
                            )
                        elif event.type == "structured_block" and event.block:
                            structured_blocks.append(event.block)
                        elif event.type == "grounding_result":
                            grounding_is_grounded = event.grounding_is_grounded
                            grounding_confidence = event.grounding_confidence
                        elif event.type == "done":
                            final_event = event
                            if event.sources:
                                final_sources = event.sources
                        yield event

                # Update query_context grounded flag from grounding result
                if query_context is not None:
                    query_context.grounded = grounding_is_grounded or False
                    log.info(
                        "chat.send_message.query_context_captured",
                        entities=[e.get("entity_text") for e in query_context.ner_entities],
                        authors=query_context.authors,
                        query_type=query_context.query_type,
                        grounded=query_context.grounded,
                    )

                # Update title with reformulated query from planning (more descriptive)
                if query_context and query_context.reformulated_query:
                    await self._repo.update_conversation(
                        conversation_id,
                        title=query_context.reformulated_query[:100],
                    )

                # Save assistant response with full step trace + grounding result
                # Sources are already filtered to cited-only by the agent's done event
                if draft_answer:
                    agent_trace = AgentTraceDTO(
                        steps=list(trace_steps.values()),
                        thinking_blocks=thinking_blocks,
                        reasoning_content="".join(reasoning_parts) or None,
                        total_duration_ms=final_event.duration_ms if final_event else None,
                        retry_count=0,
                        grounding_is_grounded=grounding_is_grounded,
                        grounding_confidence=grounding_confidence,
                    )

                    # Build token usage from agent's done event
                    token_usage = None
                    if final_event and final_event.total_tokens and final_event.total_tokens > 0:
                        token_usage = TokenUsageDTO(
                            prompt=final_event.prompt_tokens or 0,
                            completion=final_event.completion_tokens or 0,
                            total=final_event.total_tokens,
                            model=counter.model,
                        )

                    assistant_msg = ChatMessageDTO(
                        conversation_id=conversation_id,
                        message_id=final_event.message_id if final_event else uuid4(),
                        role="assistant",
                        content=draft_answer,
                        sources=final_sources,
                        agent_trace=agent_trace,
                        structured_content=structured_blocks or None,
                        token_usage=token_usage,
                        query_context=query_context,
                        created_at=datetime.now(UTC),
                    )
                    await self._repo.append_message(assistant_msg)
            finally:
                await self._record_chat_usage(
                    counter,
                    workspace_id,
                    owner_id,
                    conversation_id,
                    final_event,
                )
        finally:
            reasoning_context.reset_reasoning_override(_reasoning_token)

    async def _safe_record(self, event: TokenUsageEvent, conversation_id: UUID) -> None:
        """Write the usage event, logging any failure with context.

        Runs *inside* the shield in ``_record_chat_usage`` so a write failure
        is caught here even if the outer await was already cancelled by a
        client disconnect — otherwise it would only surface as an
        unretrieved-task GC warning with no context.
        """
        try:
            await self._usage.record(event)
        except Exception:
            log.exception("chat.usage.record_failed", conversation_id=str(conversation_id))

    async def _record_chat_usage(
        self,
        counter: TokenCounter,
        workspace_id: UUID,
        owner_id: UUID,
        conversation_id: UUID,
        final_event: AgentEvent | None,
    ) -> None:
        """Single write point for chat token accounting.

        Runs in ``finally`` so errors and client disconnects still record.
        Shielded: a disconnect cancels this generator mid-write, but the
        ledger write must land — quota must not be evadable by hanging up.
        """
        if counter.total_tokens <= 0:
            return
        message_id = final_event.message_id if final_event else None
        event = TokenUsageEvent(
            event_id=f"chat:{message_id}" if message_id else None,
            workspace_id=workspace_id,
            user_id=owner_id,
            kind="chat",
            source="chat_message",
            prompt=counter.prompt_tokens,
            completion=counter.completion_tokens,
            total=counter.total_tokens,
            model=counter.model,
            ref=str(conversation_id),
            created_at=datetime.now(UTC),
        )
        with contextlib.suppress(asyncio.CancelledError):
            # our await was cancelled; the shielded write completes anyway
            await asyncio.shield(self._safe_record(event, conversation_id))


class RecordFeedbackUseCase:
    """Record thumbs-up/thumbs-down feedback on a chat message.

    Validates that the conversation exists and belongs to the caller.
    """

    def __init__(self, chat_repository: ChatRepository) -> None:
        self._repo = chat_repository

    async def execute(
        self,
        feedback: ChatFeedbackDTO,
    ) -> Result[None, AppError]:
        try:
            # Verify conversation exists and belongs to the caller
            conversation = await self._repo.get_conversation(
                feedback.conversation_id,
                workspace_id=feedback.workspace_id,
                owner_id=feedback.user_id,
            )
            if conversation is None:
                return Failure(AppError("not_found", "Conversation not found"))

            await self._repo.record_feedback(feedback)
            return Success(None)
        except Exception as e:
            log.exception("chat.feedback.record_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to record feedback: {e!s}"))
