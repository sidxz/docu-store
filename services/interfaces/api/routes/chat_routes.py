"""Chat routes for the agentic RAG chat system."""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from lagom import Container
from returns.result import Failure
from sentinel_auth import RequestAuth

from application.dtos.chat_dtos import (
    ConversationDTO,
    CreateConversationRequest,
    ListConversationsRequest,
    SendMessageRequest,
)
from application.use_cases.chat_use_cases import (
    CreateConversationUseCase,
    DeleteConversationUseCase,
    GetConversationUseCase,
    ListConversationsUseCase,
    SendMessageUseCase,
)
from interfaces.api.middleware import handle_use_case_errors
from interfaces.api.routes.helpers import get_allowed_artifact_ids as _get_allowed_artifact_ids
from interfaces.dependencies import get_auth, get_container

logger = structlog.get_logger()

router = APIRouter(prefix="/chat", tags=["chat"])


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


@router.get("/{conversation_id}", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def get_conversation(
    conversation_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    skip: int = 0,
    limit: int = 100,
) -> dict:
    """Get a conversation with its messages."""
    use_case = container[GetConversationUseCase]
    return await use_case.execute(
        conversation_id=conversation_id,
        workspace_id=auth.workspace_id,
        skip=skip,
        limit=limit,
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Delete a conversation and all its messages."""
    use_case = container[DeleteConversationUseCase]
    result = await use_case.execute(
        conversation_id=conversation_id,
        workspace_id=auth.workspace_id,
    )
    if isinstance(result, Failure):
        error = result.failure()
        if error.category == "not_found":
            raise HTTPException(status_code=404, detail="Conversation not found")
        raise HTTPException(status_code=500, detail="Failed to delete conversation")


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
        try:
            async for event in use_case.execute(
                conversation_id=conversation_id,
                workspace_id=auth.workspace_id,
                owner_id=auth.user_id,
                message=request.message,
                allowed_artifact_ids=allowed_artifact_ids,
            ):
                event_type = _map_event_type(event.type)
                data = event.model_dump(mode="json", exclude_none=True)
                yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        except Exception as exc:
            logger.exception("chat.stream.error", error=str(exc))
            error_data = {"type": "error", "error_message": str(exc)}
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _map_event_type(event_type: str) -> str:
    """Map internal event types to SSE event names."""
    mapping = {
        "step_started": "agent_step",
        "step_completed": "agent_step",
        "retrieval_results": "retrieval_results",
        "token": "token",
        "structured_block": "structured_block",
        "done": "done",
        "error": "error",
    }
    return mapping.get(event_type, event_type)
