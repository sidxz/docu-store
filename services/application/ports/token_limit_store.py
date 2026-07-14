"""Port for admin-configured monthly token limits."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from application.dtos.usage_dtos import TokenLimitEntry


class TokenLimitStore(Protocol):
    """Workspace token limits: per-user override rows plus a workspace-default row.

    Rows are keyed by (workspace_id, user_id); user_id=None is the workspace
    default. Resolution (override ?? default ?? unlimited) lives in the
    application layer, not here — this port is dumb CRUD.
    """

    async def get(self, workspace_id: UUID, user_id: UUID | None) -> TokenLimitEntry | None: ...

    async def list_for_workspace(self, workspace_id: UUID) -> list[TokenLimitEntry]: ...

    async def set(
        self,
        workspace_id: UUID,
        user_id: UUID | None,
        limit: int | None,
        updated_by: UUID,
    ) -> None:
        """Upsert one row. ``user_id=None`` sets the workspace default."""
        ...

    async def delete(self, workspace_id: UUID, user_id: UUID) -> None:
        """Remove a per-user override (the default is cleared by set(None))."""
        ...

    async def ensure_indexes(self) -> None: ...
