"""Use cases for the agentic RAG chat system."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
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
    ContentBlockDTO,
    ConversationDetailDTO,
    ConversationDTO,
    QueryContextDTO,
    SourceCitationDTO,
    ThinkingBlockDTO,
    TokenUsageDTO,
)
from application.dtos.errors import AppError

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
    ) -> Result[list[ConversationDTO], AppError]:
        try:
            conversations = await self._repo.list_conversations(
                workspace_id=workspace_id,
                owner_id=owner_id,
                skip=skip,
                limit=limit,
                is_archived=is_archived,
            )
            return Success(conversations)
        except Exception as e:
            log.exception("chat.conversations.list_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to list conversations: {e!s}"))


class GetConversationUseCase:
    """Get a conversation with its messages."""

    def __init__(self, chat_repository: ChatRepository) -> None:
        self._repo = chat_repository

    async def execute(
        self,
        conversation_id: UUID,
        workspace_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Result[ConversationDetailDTO, AppError]:
        try:
            conversation = await self._repo.get_conversation(
                conversation_id,
                workspace_id=workspace_id,
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
    ) -> Result[bool, AppError]:
        try:
            deleted = await self._repo.delete_conversation(
                conversation_id,
                workspace_id=workspace_id,
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
    ) -> None:
        self._repo = chat_repository
        self._agent = chat_agent

    async def execute(
        self,
        conversation_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        message: str,
        allowed_artifact_ids: list[UUID] | None = None,
        mode: Literal["quick", "thinking", "deep_thinking"] | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        # Verify conversation exists
        conversation = await self._repo.get_conversation(
            conversation_id,
            workspace_id=workspace_id,
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


class RecordFeedbackUseCase:
    """Record thumbs-up/thumbs-down feedback on a chat message.

    Validates that the conversation exists and belongs to the caller's workspace.
    """

    def __init__(self, chat_repository: ChatRepository) -> None:
        self._repo = chat_repository

    async def execute(
        self,
        feedback: ChatFeedbackDTO,
    ) -> Result[None, AppError]:
        try:
            # Verify conversation exists and belongs to the workspace
            conversation = await self._repo.get_conversation(
                feedback.conversation_id,
                workspace_id=feedback.workspace_id,
            )
            if conversation is None:
                return Failure(AppError("not_found", "Conversation not found"))

            await self._repo.record_feedback(feedback)
            return Success(None)
        except Exception as e:
            log.exception("chat.feedback.record_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to record feedback: {e!s}"))
