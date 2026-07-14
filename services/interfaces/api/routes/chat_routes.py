"""Chat routes for the agentic RAG chat system."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from lagom import Container
from pydantic import BaseModel, Field
from sentinel_auth import RequestAuth

from application.dtos.chat_dtos import (
    ChatFeedbackDTO,
    ConversationDetailDTO,
    ConversationDTO,
    RecentConversationDTO,
    TokenUsageDTO,
)
from application.use_cases.chat_folder_use_cases import SetConversationFolderUseCase
from application.use_cases.chat_use_cases import (
    CreateConversationUseCase,
    DeleteConversationUseCase,
    GetConversationUseCase,
    GetUserTokenUsageUseCase,
    ListConversationsUseCase,
    ListRecentConversationsUseCase,
    RecordFeedbackUseCase,
    SendMessageUseCase,
)
from interfaces.api.middleware import handle_use_case_errors
from interfaces.api.routes.helpers import ensure_within_quota
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
    reasoning: (
        dict[Literal["synthesis", "retrieval", "base"], Literal["off", "low", "medium", "high"]]
        | None
    ) = Field(
        default=None,
        description="Per-lane reasoning override; absent lanes use the server default.",
    )


class FeedbackRequest(BaseModel):
    """Request to record feedback on a message."""

    feedback: Literal["positive", "negative"]


class SetFolderRequest(BaseModel):
    """Request to move a conversation into a folder.

    ``folder_id`` is required but nullable: explicit null unfiles the
    conversation; omitting the field is a 422 (guards PATCH {} from
    silently unfiling).
    """

    folder_id: UUID | None


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
    folder_id: UUID | None = None,
) -> list[ConversationDTO]:
    """List conversations for the current user. Pass ``folder_id`` for a folder view."""
    use_case = container[ListConversationsUseCase]
    return await use_case.execute(
        workspace_id=auth.workspace_id,
        owner_id=auth.user_id,
        skip=skip,
        limit=limit,
        is_archived=is_archived,
        folder_id=folder_id,
    )


@router.get("/usage", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def get_user_token_usage(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
    kind: Annotated[str | None, Query(pattern="^(chat|ingestion)$")] = None,
) -> TokenUsageDTO:
    """Current user's token usage from the ledger (all-time unless ``days`` given)."""
    use_case = container[GetUserTokenUsageUseCase]
    return await use_case.execute(
        workspace_id=auth.workspace_id,
        owner_id=auth.user_id,
        days=days,
        kind=kind,
    )


@router.get("/recent", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def list_recent_conversations(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    limit: int = 5,
) -> list[RecentConversationDTO]:
    """Recent conversations enriched with a dashboard summary."""
    use_case = container[ListRecentConversationsUseCase]
    return await use_case.execute(
        workspace_id=auth.workspace_id,
        owner_id=auth.user_id,
        limit=limit,
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


@router.patch("/{conversation_id}", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def set_conversation_folder(
    conversation_id: UUID,
    request: SetFolderRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> ConversationDTO:
    """Move a conversation into a folder (``folder_id: null`` removes it from its folder)."""
    use_case = container[SetConversationFolderUseCase]
    return await use_case.execute(
        conversation_id=conversation_id,
        workspace_id=auth.workspace_id,
        owner_id=auth.user_id,
        folder_id=request.folder_id,
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
    await ensure_within_quota(auth, container)
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
