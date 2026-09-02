"""Chat routes for the agentic RAG chat system."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

import structlog
from duar_auth import RequestAuth
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from lagom import Container
from pydantic import BaseModel, Field
from returns.result import Failure, Success

from application.dtos.chat_dtos import (
    ChatFeedbackDTO,
    ConversationDetailDTO,
    ConversationDTO,
    RecentConversationDTO,
)
from application.dtos.usage_dtos import UserTokenUsageResponse
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
from domain.value_objects.chat_surface import ChatSurface
from infrastructure.chat.run_registry import ChatRunRegistry, RunAlreadyActiveError
from interfaces.api.middleware import handle_use_case_errors
from interfaces.api.routes.helpers import (
    _map_app_error_to_http_exception,
    ensure_llm_configured,
    ensure_within_quota,
)
from interfaces.api.routes.helpers import get_allowed_artifact_ids as _get_allowed_artifact_ids
from interfaces.dependencies import get_auth, get_container, llm_user_scope

logger = structlog.get_logger()

router = APIRouter(prefix="/chat", tags=["chat"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""

    title: str | None = None
    surface: ChatSurface = ChatSurface.RESEARCH


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""

    message: str = Field(..., min_length=1, max_length=10000)
    mode: Literal["quick", "thinking", "deep_thinking", "literature"] | None = Field(
        default=None,
        description="Pipeline mode. 'quick' = 4-step, 'thinking' = 5-stage, 'deep_thinking' = thinking + page images, 'literature' = published papers rather than this corpus. None = server default.",
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
        surface=request.surface,
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
    surface: ChatSurface | None = None,
) -> list[ConversationDTO]:
    """List conversations for the current user. Pass ``folder_id`` for a folder view.

    ``surface`` keeps the two chat surfaces apart: Deep Research and Literature
    share a store but not a history, since a question asked of the corpus and one
    asked of the literature are not the same kind of thing to come back to.
    Omitting ``surface`` returns every surface -- that is what a folder view
    wants, since a folder is an explicit bucket the user dragged things into
    and must show everything filed there, not just one surface's slice of it.
    """
    use_case = container[ListConversationsUseCase]
    return await use_case.execute(
        workspace_id=auth.workspace_id,
        owner_id=auth.user_id,
        surface=surface,
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
) -> UserTokenUsageResponse:
    """Current user's token usage from the ledger (all-time unless ``days`` given)."""
    use_case = container[GetUserTokenUsageUseCase]
    return await use_case.execute(
        workspace_id=auth.workspace_id,
        owner_id=auth.user_id,
        days=days,
        kind=kind,
        exempt=auth.is_admin,  # admins bypass enforcement; don't render a limit for them
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
async def get_conversation(
    conversation_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    skip: int = 0,
    limit: int = 100,
) -> ConversationDetailDTO:
    """Get a conversation with its messages."""
    use_case = container[GetConversationUseCase]
    result = await use_case.execute(
        conversation_id=conversation_id,
        workspace_id=auth.workspace_id,
        owner_id=auth.user_id,
        skip=skip,
        limit=limit,
    )
    # execute() returns a Result in production (Success is immutable, so we
    # unwrap before setting active_run below); test doubles may hand back the
    # DTO directly.
    if isinstance(result, Failure):
        raise _map_app_error_to_http_exception(result.failure())
    detail = result.unwrap() if isinstance(result, Success) else result
    run = container[ChatRunRegistry].active(conversation_id)
    detail.active_run = run is not None and not run.done
    return detail


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
@handle_use_case_errors
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
        owner_id=auth.user_id,
    )
    if isinstance(result, Success):
        # Only after a confirmed delete — a cross-workspace 404 must never
        # be able to cancel another tenant's run.
        container[ChatRunRegistry].stop(conversation_id)
    return result


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


@router.post(
    "/{conversation_id}/messages",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(llm_user_scope)],
)
async def send_message(
    conversation_id: UUID,
    request: SendMessageRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> StreamingResponse:
    """Send a message and stream the agent response via SSE.

    Generation is decoupled from this connection: a background run keeps
    going (and persists its answer) even if the client disconnects. Frames
    carry ``id: <seq>`` so ``GET .../messages/stream`` can replay and tail.

    Returns a text/event-stream with the following event types:
    - agent_step: Step progress (started/completed)
    - retrieval_results: Retrieved source citations
    - token: Streaming answer tokens
    - structured_block: Rich content blocks (table, molecule, etc.)
    - done: Final event with message ID and metadata
    - error: Error event

    Raises 409 if a response is already being generated for this conversation.
    """
    await ensure_llm_configured(auth, container)
    await ensure_within_quota(auth, container)
    allowed_artifact_ids = await _get_allowed_artifact_ids(auth)

    use_case = container[SendMessageUseCase]
    registry = container[ChatRunRegistry]
    try:
        registry.start(
            conversation_id=conversation_id,
            workspace_id=auth.workspace_id,
            owner_id=auth.user_id,
            agen=use_case.execute(
                conversation_id=conversation_id,
                workspace_id=auth.workspace_id,
                owner_id=auth.user_id,
                message=request.message,
                allowed_artifact_ids=allowed_artifact_ids,
                mode=request.mode,
                reasoning=request.reasoning,
            ),
        )
    except RunAlreadyActiveError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A response is already being generated for this conversation.",
        ) from None

    return StreamingResponse(
        registry.subscribe(conversation_id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


def _owned_run(registry: ChatRunRegistry, conversation_id: UUID, auth: RequestAuth):
    """The caller's run for this conversation, or raise 404."""
    run = registry.active(conversation_id)
    if run is None or run.workspace_id != auth.workspace_id or run.owner_id != auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active run for this conversation.",
        )
    return run


@router.get("/{conversation_id}/messages/stream", status_code=status.HTTP_200_OK)
async def resume_message_stream(
    conversation_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    after: int = -1,
) -> StreamingResponse:
    """Reattach to an in-flight (or just-finished) run: replay frames past
    ``after``, then tail live until done.
    """
    registry = container[ChatRunRegistry]
    _owned_run(registry, conversation_id, auth)
    return StreamingResponse(
        registry.subscribe(conversation_id, after=after),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.delete("/{conversation_id}/run", status_code=status.HTTP_204_NO_CONTENT)
async def stop_message_run(
    conversation_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Stop an in-flight run. Discards the partial answer (nothing persists);
    needed because disconnecting no longer cancels generation.
    """
    registry = container[ChatRunRegistry]
    _owned_run(registry, conversation_id, auth)
    registry.stop(conversation_id)


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
