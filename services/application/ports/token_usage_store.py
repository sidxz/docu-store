"""Port for the append-only token usage ledger."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from application.dtos.chat_dtos import TokenUsageDTO
from application.dtos.usage_dtos import MemberTokenUsage, TokenUsageEvent


class TokenUsageStore(Protocol):
    """Append-only ledger of LLM token usage, independent of chat CRUD.

    Deleting a conversation must never change recorded usage — that is the
    ledger's reason to exist (quota integrity).
    """

    async def record(self, event: TokenUsageEvent) -> None:
        """Append one usage event (upsert when ``event.event_id`` is set)."""
        ...

    async def sum_for_user(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        since: datetime | None = None,
        kind: str | None = None,
    ) -> TokenUsageDTO:
        """Sum a user's usage, optionally windowed and filtered by kind."""
        ...

    async def usage_by_member(
        self,
        workspace_id: UUID,
        *,
        since: datetime,
    ) -> list[MemberTokenUsage]:
        """Per-member usage in a workspace since ``since``, split by kind."""
        ...

    async def ensure_indexes(self) -> None: ...
