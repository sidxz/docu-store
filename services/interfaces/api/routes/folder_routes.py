"""Chat folder routes (per-user, per-workspace, flat, non-nested).

Mounted at top-level ``/folders`` rather than ``/chat/folders`` — the latter
would be shadowed by ``GET /chat/{conversation_id}`` (the UUID param route wins
and 422s on the literal "folders").
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from lagom import Container
from pydantic import BaseModel, StringConstraints
from sentinel_auth import RequestAuth

from application.dtos.chat_dtos import ChatFolderDTO
from application.use_cases.chat_folder_use_cases import (
    CreateFolderUseCase,
    DeleteFolderUseCase,
    ListFoldersUseCase,
    RenameFolderUseCase,
)
from interfaces.api.middleware import handle_use_case_errors
from interfaces.dependencies import get_auth, get_container

router = APIRouter(prefix="/folders", tags=["folders"])

FolderName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CreateFolderRequest(BaseModel):
    """Request to create a chat folder."""

    name: FolderName


class RenameFolderRequest(BaseModel):
    """Request to rename a chat folder."""

    name: FolderName


@router.get("", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def list_folders(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> list[ChatFolderDTO]:
    """List the current user's chat folders with chat counts."""
    use_case = container[ListFoldersUseCase]
    return await use_case.execute(
        workspace_id=auth.workspace_id,
        owner_id=auth.user_id,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
@handle_use_case_errors
async def create_folder(
    request: CreateFolderRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> ChatFolderDTO:
    """Create a chat folder."""
    use_case = container[CreateFolderUseCase]
    return await use_case.execute(
        workspace_id=auth.workspace_id,
        owner_id=auth.user_id,
        name=request.name,
    )


@router.patch("/{folder_id}", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def rename_folder(
    folder_id: UUID,
    request: RenameFolderRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> ChatFolderDTO:
    """Rename a chat folder."""
    use_case = container[RenameFolderUseCase]
    return await use_case.execute(
        workspace_id=auth.workspace_id,
        owner_id=auth.user_id,
        folder_id=folder_id,
        name=request.name,
    )


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
@handle_use_case_errors
async def delete_folder(
    folder_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Delete a folder; its chats are unfiled, not deleted."""
    use_case = container[DeleteFolderUseCase]
    return await use_case.execute(
        workspace_id=auth.workspace_id,
        owner_id=auth.user_id,
        folder_id=folder_id,
    )
