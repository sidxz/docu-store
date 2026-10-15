"""Which embedding model a workspace uses (self-serve).

One model per workspace: its documents and its queries must share a vector
space. Absent → the server model. Changing it means re-embedding the workspace.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID


@dataclass(frozen=True)
class WorkspaceEmbeddingConfig:
    model: str  # "local" or a key of application.services.embedding_models.EMBEDDING_MODELS
    updated_by: UUID | None = None
    updated_at: datetime | None = None


class WorkspaceEmbeddingConfigStore(Protocol):
    async def get(self, workspace_id: UUID) -> WorkspaceEmbeddingConfig | None: ...

    async def set(self, workspace_id: UUID, model: str, *, updated_by: UUID) -> None: ...
