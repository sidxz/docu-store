"""Port for chat conversation and message persistence."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from application.dtos.chat_dtos import ChatMessageDTO, ConversationDTO


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
    ) -> ConversationDTO | None: ...

    async def list_conversations(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        skip: int = 0,
        limit: int = 20,
        is_archived: bool = False,
    ) -> list[ConversationDTO]: ...

    async def delete_conversation(
        self,
        conversation_id: UUID,
        workspace_id: UUID | None = None,
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

    async def ensure_indexes(self) -> None: ...
