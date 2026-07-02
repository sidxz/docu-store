"""Chat routes for the agentic RAG chat system."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from lagom import Container
from pydantic import BaseModel, Field
from sentinel_auth import RequestAuth

from application.dtos.chat_dtos import (
    ChatFeedbackDTO,
    ConversationDetailDTO,
    ConversationDTO,
    TokenUsageDTO,
)
from application.use_cases.chat_use_cases import (
    CreateConversationUseCase,
    DeleteConversationUseCase,
    GetConversationUseCase,
    GetUserTokenUsageUseCase,
    ListConversationsUseCase,
    RecordFeedbackUseCase,
    SendMessageUseCase,
)
from interfaces.api.middleware import handle_use_case_errors
from interfaces.api.routes.helpers import get_allowed_artifact_ids as _get_allowed_artifact_ids
from interfaces.dependencies import get_auth, get_container

logger = structlog.get_logger()

router = APIRouter(prefix="/chat", tags=["chat"])


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""

    title: str | None = None


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""

    message: str = Field(..., min_length=1, max_length=10000)
    mode: Literal["quick", "thinking", "deep_thinking"] | None = Field(
        default=None,
        description="Pipeline mode. 'quick' = 4-step, 'thinking' = 5-stage, 'deep_thinking' = thinking + page images. None = server default.",
    )
    reasoning: dict[Literal["synthesis", "retrieval", "base"],
                    Literal["off", "low", "medium", "high"]] | None = Field(
        default=None,
        description="Per-lane reasoning override; absent lanes use the server default.",
    )


class FeedbackRequest(BaseModel):
    """Request to record feedback on a message."""

    feedback: Literal["positive", "negative"]


@router.post("", status_code=status.HTTP_201_CREATED)
@handle_use_case_errors
async def create_conversation(
    request: CreateConversationRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> ConversationDTO:
    """Create a new chat conversation."""
    use_case = container[CreateConversationUseCase]
    return await use_case.execute(
        workspace_id=auth.workspace_id,
        owner_id=auth.user_id,
        title=request.title,
    )


@router.get("", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def list_conversations(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    skip: int = 0,
    limit: int = 20,
    is_archived: bool = False,
) -> list[ConversationDTO]:
    """List conversations for the current user."""
    use_case = container[ListConversationsUseCase]
    return await use_case.execute(
        workspace_id=auth.workspace_id,
        owner_id=auth.user_id,
        skip=skip,
        limit=limit,
        is_archived=is_archived,
    )


@router.get("/usage", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def get_user_token_usage(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> TokenUsageDTO:
    """Total token usage across the current user's conversations (usage badge)."""
    use_case = container[GetUserTokenUsageUseCase]
    return await use_case.execute(
        workspace_id=auth.workspace_id,
        owner_id=auth.user_id,
    )


@router.get("/{conversation_id}", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def get_conversation(
    conversation_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    skip: int = 0,
    limit: int = 100,
) -> ConversationDetailDTO:
    """Get a conversation with its messages."""
    use_case = container[GetConversationUseCase]
    return await use_case.execute(
        conversation_id=conversation_id,
        workspace_id=auth.workspace_id,
        skip=skip,
        limit=limit,
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
@handle_use_case_errors
async def delete_conversation(
    conversation_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Delete a conversation and all its messages."""
    use_case = container[DeleteConversationUseCase]
    return await use_case.execute(
        conversation_id=conversation_id,
        workspace_id=auth.workspace_id,
    )


@router.post("/{conversation_id}/messages", status_code=status.HTTP_200_OK)
async def send_message(
    conversation_id: UUID,
    request: SendMessageRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> StreamingResponse:
    """Send a message and stream the agent response via SSE.

    Returns a text/event-stream with the following event types:
    - agent_step: Step progress (started/completed)
    - retrieval_results: Retrieved source citations
    - token: Streaming answer tokens
    - structured_block: Rich content blocks (table, molecule, etc.)
    - done: Final event with message ID and metadata
    - error: Error event
    """
    allowed_artifact_ids = await _get_allowed_artifact_ids(auth)

    use_case = container[SendMessageUseCase]

    async def event_stream():
        t0 = time.monotonic()
        step_count = 0
        effective_mode = request.mode or "thinking"
        try:
            async for event in use_case.execute(
                conversation_id=conversation_id,
                workspace_id=auth.workspace_id,
                owner_id=auth.user_id,
                message=request.message,
                allowed_artifact_ids=allowed_artifact_ids,
                mode=request.mode,
                reasoning=request.reasoning,
            ):
                if event.type == "step_started":
                    step_count += 1
                event_type = _map_event_type(event.type)
                data = event.model_dump(mode="json", exclude_none=True)
                yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        except Exception as exc:
            logger.exception("chat.stream.error", error=str(exc))
            error_data = {"type": "error", "error_message": str(exc)}
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
        finally:
            duration_ms = round((time.monotonic() - t0) * 1000, 2)
            logger.info(
                "chat.response_completed",
                duration_ms=duration_ms,
                mode=effective_mode,
                step_count=step_count,
                conversation_id=str(conversation_id),
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{conversation_id}/messages/{message_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
)
@handle_use_case_errors
async def record_feedback(
    conversation_id: UUID,
    message_id: UUID,
    request: FeedbackRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Record thumbs-up/thumbs-down feedback on a chat message."""
    use_case = container[RecordFeedbackUseCase]
    feedback = ChatFeedbackDTO(
        conversation_id=conversation_id,
        message_id=message_id,
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        feedback=request.feedback,
        created_at=datetime.now(UTC),
    )
    return await use_case.execute(feedback)


def _map_event_type(event_type: str) -> str:
    """Map internal event types to SSE event names."""
    mapping = {
        "step_started": "agent_step",
        "step_completed": "agent_step",
        "retrieval_results": "retrieval_results",
        "token": "token",
        "reasoning_token": "reasoning_token",
        "structured_block": "structured_block",
        "grounding_result": "grounding_result",
        "query_context": "query_context",
        "done": "done",
        "error": "error",
    }
    return mapping.get(event_type, event_type)
