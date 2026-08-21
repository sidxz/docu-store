"""Use cases for per-user chat folders (flat, non-nested)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog
from pymongo.errors import DuplicateKeyError
from returns.result import Failure, Result, Success

from application.dtos.chat_dtos import ChatFolderDTO, ConversationDTO
from application.dtos.errors import AppError

if TYPE_CHECKING:
    from application.ports.chat_repository import ChatRepository

log = structlog.get_logger(__name__)


class ListFoldersUseCase:
    """List the user's chat folders, each with its chat count."""

    def __init__(self, chat_repository: ChatRepository) -> None:
        self._repo = chat_repository

    async def execute(
        self,
        workspace_id: UUID,
        owner_id: UUID,
    ) -> Result[list[ChatFolderDTO], AppError]:
        try:
            folders = await self._repo.list_folders(workspace_id, owner_id)
            return Success(folders)
        except Exception as e:
            log.exception("chat.folders.list_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to list folders: {e!s}"))


class CreateFolderUseCase:
    """Create a new chat folder."""

    def __init__(self, chat_repository: ChatRepository) -> None:
        self._repo = chat_repository

    async def execute(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        name: str,
    ) -> Result[ChatFolderDTO, AppError]:
        try:
            name = name.strip()
            if not name:
                return Failure(AppError("validation", "Folder name is required"))
            now = datetime.now(UTC)
            folder = ChatFolderDTO(
                folder_id=uuid4(),
                workspace_id=workspace_id,
                owner_id=owner_id,
                name=name,
                created_at=now,
                updated_at=now,
            )
            created = await self._repo.create_folder(folder)
            log.info("chat.folder.created", id=str(created.folder_id))
            return Success(created)
        except DuplicateKeyError:
            # ponytail: byte-exact uniqueness ("Research" vs "research" both allowed); case-insensitive needs an index collation.
            return Failure(AppError("validation", "A folder with this name already exists"))
        except Exception as e:
            log.exception("chat.folder.create_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to create folder: {e!s}"))


class RenameFolderUseCase:
    """Rename a chat folder."""

    def __init__(self, chat_repository: ChatRepository) -> None:
        self._repo = chat_repository

    async def execute(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        folder_id: UUID,
        name: str,
    ) -> Result[ChatFolderDTO, AppError]:
        try:
            name = name.strip()
            if not name:
                return Failure(AppError("validation", "Folder name is required"))
            folder = await self._repo.rename_folder(workspace_id, owner_id, folder_id, name)
            if folder is None:
                return Failure(AppError("not_found", "Folder not found"))
            return Success(folder)
        except DuplicateKeyError:
            return Failure(AppError("validation", "A folder with this name already exists"))
        except Exception as e:
            log.exception("chat.folder.rename_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to rename folder: {e!s}"))


class DeleteFolderUseCase:
    """Delete a folder; its chats are unfiled, never deleted."""

    def __init__(self, chat_repository: ChatRepository) -> None:
        self._repo = chat_repository

    async def execute(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        folder_id: UUID,
    ) -> Result[bool, AppError]:
        try:
            await self._repo.clear_folder(workspace_id, owner_id, folder_id)
            deleted = await self._repo.delete_folder(workspace_id, owner_id, folder_id)
            if not deleted:
                return Failure(AppError("not_found", "Folder not found"))
            log.info("chat.folder.deleted", id=str(folder_id))
            return Success(True)
        except Exception as e:
            log.exception("chat.folder.delete_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to delete folder: {e!s}"))


class SetConversationFolderUseCase:
    """Move a conversation into a folder, or None to unfile it.

    Bumps the source and destination folder dates (membership changed) but
    leaves the conversation's own updated_at untouched, so filing does not
    reorder the recency-sorted Recent list.
    """

    def __init__(self, chat_repository: ChatRepository) -> None:
        self._repo = chat_repository

    async def execute(
        self,
        conversation_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        folder_id: UUID | None,
    ) -> Result[ConversationDTO, AppError]:
        try:
            conv = await self._repo.get_conversation(
                conversation_id, workspace_id=workspace_id, owner_id=owner_id
            )
            if conv is None:
                return Failure(AppError("not_found", "Conversation not found"))

            old = conv.folder_id
            if folder_id == old:
                return Success(conv)  # already there — no write, no date bump

            if folder_id is not None:
                dest = await self._repo.get_folder(workspace_id, owner_id, folder_id)
                if dest is None:
                    return Failure(AppError("not_found", "Folder not found"))

            moved = await self._repo.set_conversation_folder(
                conversation_id,
                folder_id,
                workspace_id,
                owner_id,
            )
            if not moved:
                # Deleted between our read and this write — don't bump folder dates.
                return Failure(AppError("not_found", "Conversation not found"))
            await self._repo.touch_folders(
                workspace_id,
                owner_id,
                [f for f in (old, folder_id) if f is not None],
            )

            conv.folder_id = folder_id
            log.info(
                "chat.conversation.folder_set",
                id=str(conversation_id),
                folder_id=str(folder_id) if folder_id else None,
            )
            return Success(conv)
        except Exception as e:
            log.exception("chat.conversation.folder_set_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to move conversation: {e!s}"))
