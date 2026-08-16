"""User preferences and activity routes.

Not event-sourced. Simple operational metadata storage.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from lagom import Container
from duar_auth import RequestAuth

from application.dtos.user_dtos import (
    RecentDocumentEntry,
    RecordDocumentOpenRequest,
    RecordSearchActivityRequest,
    SearchHistoryEntry,
    UpdatePreferencesRequest,
    UserPreferencesDTO,
)
from application.ports.repositories.user_activity_store import UserActivityStore
from application.ports.repositories.user_preferences_store import UserPreferencesStore
from interfaces.dependencies import get_auth, get_container

router = APIRouter(prefix="/user", tags=["user"])


# ── Preferences ──────────────────────────────────────────────────────────────


@router.get("/preferences", status_code=status.HTTP_200_OK)
async def get_preferences(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> UserPreferencesDTO:
    store = container[UserPreferencesStore]
    return await store.get_preferences(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
    )


@router.patch("/preferences", status_code=status.HTTP_200_OK)
async def update_preferences(
    body: UpdatePreferencesRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> UserPreferencesDTO:
    store = container[UserPreferencesStore]
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return await store.get_preferences(
            workspace_id=auth.workspace_id,
            user_id=auth.user_id,
        )
    return await store.update_preferences(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        updates=updates,
    )


# ── Activity Recording ───────────────────────────────────────────────────────


@router.post("/activity/search", status_code=status.HTTP_204_NO_CONTENT)
async def record_search(
    body: RecordSearchActivityRequest,
    background_tasks: BackgroundTasks,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    store = container[UserActivityStore]
    background_tasks.add_task(
        store.record_search,
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        query_text=body.query_text,
        search_mode=body.search_mode,
        result_count=body.result_count,
    )


@router.post("/activity/document", status_code=status.HTTP_204_NO_CONTENT)
async def record_document_open(
    body: RecordDocumentOpenRequest,
    background_tasks: BackgroundTasks,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    store = container[UserActivityStore]
    background_tasks.add_task(
        store.record_document_open,
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        artifact_id=body.artifact_id,
        artifact_title=body.artifact_title,
    )


# ── Activity Deletion ─────────────────────────────────────────────────────────


@router.delete("/activity/searches", status_code=status.HTTP_204_NO_CONTENT)
async def clear_search_history(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Delete all search history for the authenticated user."""
    store = container[UserActivityStore]
    await store.clear_search_history(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
    )


@router.delete("/activity/searches/{query_text}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_search_entry(
    query_text: str,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Delete a single search history entry by query text."""
    store = container[UserActivityStore]
    await store.delete_search_entry(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        query_text=query_text,
    )


# ── Activity Queries ─────────────────────────────────────────────────────────


@router.get("/activity/searches", status_code=status.HTTP_200_OK)
async def get_recent_searches(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    limit: int = Query(default=20, ge=1, le=100),
) -> list[SearchHistoryEntry]:
    store = container[UserActivityStore]
    return await store.get_recent_searches(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        limit=limit,
    )


@router.get("/activity/documents", status_code=status.HTTP_200_OK)
async def get_recent_documents(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    limit: int = Query(default=20, ge=1, le=100),
) -> list[RecentDocumentEntry]:
    store = container[UserActivityStore]
    return await store.get_recent_documents(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        limit=limit,
    )
