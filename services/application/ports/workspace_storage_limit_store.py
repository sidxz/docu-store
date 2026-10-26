"""Storage limit a workspace admin sets for the whole workspace.

Unset → only the deployment cap (``MAX_WORKSPACE_STORAGE_MB``) applies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID


class WorkspaceStorageLimitStore(Protocol):
    async def get_limit(self, workspace_id: UUID) -> int | None: ...

    async def set_limit(
        self, workspace_id: UUID, limit_bytes: int | None, *, updated_by: UUID
    ) -> None: ...
