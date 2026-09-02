"""Port for chat conversation and message persistence."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from application.dtos.chat_dtos import (
    ChatFeedbackDTO,
    ChatFolderDTO,
    ChatMessageDTO,
    ConversationDTO,
)
from domain.value_objects.chat_surface import ChatSurface


class ChatRepository(Protocol):
    """Repository for chat conversations and messages.

    Conversations are mutable operational data stored in MongoDB,
    NOT event-sourced aggregates.
    """

    async def create_conversation(
        self,
        conversation: ConversationDTO,
    ) -> ConversationDTO: ...

    async def get_conversation(
        self,
        conversation_id: UUID,
        workspace_id: UUID | None = None,
        owner_id: UUID | None = None,
    ) -> ConversationDTO | None:
        """Fetch a conversation. When owner_id is given, only that owner's
        conversation matches — callers acting for a request user MUST pass it;
        conversations are private to their owner.
        """
        ...

    async def list_conversations(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        skip: int = 0,
        limit: int = 20,
        is_archived: bool = False,
        folder_id: UUID | None = None,
        # None means every surface. A folder view wants that — things are filed
        # into a folder deliberately, so it must show what was put there — while
        # the sidebar passes a surface explicitly to keep the histories apart.
        surface: ChatSurface | None = None,
    ) -> list[ConversationDTO]: ...

    async def list_recent_conversations(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        limit: int,
    ) -> list[ConversationDTO]: ...

    async def delete_conversation(
        self,
        conversation_id: UUID,
        workspace_id: UUID | None = None,
        owner_id: UUID | None = None,
    ) -> bool: ...

    async def update_conversation(
        self,
        conversation_id: UUID,
        *,
        title: str | None = None,
        message_count: int | None = None,
        model_used: str | None = None,
        is_archived: bool | None = None,
    ) -> bool: ...

    async def set_conversation_folder(
        self,
        conversation_id: UUID,
        folder_id: UUID | None,
        workspace_id: UUID,
        owner_id: UUID,
    ) -> bool:
        """Move a conversation into a folder (or None to unfile).

        Scoped to the owner. Returns False when no conversation matched.
        Does NOT bump the conversation's updated_at — filing must not reorder
        the recency-sorted Recent list.
        """
        ...

    # --- Folders (per-user, per-workspace, flat) ---

    async def create_folder(self, folder: ChatFolderDTO) -> ChatFolderDTO: ...

    async def list_folders(
        self,
        workspace_id: UUID,
        owner_id: UUID,
    ) -> list[ChatFolderDTO]:
        """Folders for the user, sorted by name, each with its chat_count."""
        ...

    async def get_folder(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        folder_id: UUID,
    ) -> ChatFolderDTO | None: ...

    async def rename_folder(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        folder_id: UUID,
        name: str,
    ) -> ChatFolderDTO | None: ...

    async def touch_folders(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        folder_ids: list[UUID],
    ) -> None:
        """Bump updated_at on the given folders (membership changed)."""
        ...

    async def delete_folder(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        folder_id: UUID,
    ) -> bool: ...

    async def clear_folder(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        folder_id: UUID,
    ) -> int:
        """Unfile every conversation in the folder. Returns count unfiled."""
        ...

    async def append_message(
        self,
        message: ChatMessageDTO,
    ) -> ChatMessageDTO: ...

    async def get_messages(
        self,
        conversation_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ChatMessageDTO]: ...

    async def get_recent_messages(
        self,
        conversation_id: UUID,
        limit: int = 10,
    ) -> list[ChatMessageDTO]: ...

    async def get_conversation_summary(
        self,
        conversation_id: UUID,
    ) -> str | None: ...

    async def save_conversation_summary(
        self,
        conversation_id: UUID,
        summary: str,
    ) -> None: ...

    async def record_feedback(
        self,
        feedback: ChatFeedbackDTO,
    ) -> None: ...

    async def get_feedback(
        self,
        conversation_id: UUID,
        message_id: UUID,
    ) -> ChatFeedbackDTO | None: ...

    async def ensure_indexes(self) -> None: ...
