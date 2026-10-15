"""MongoDB adapter for WorkspaceEmbeddingConfigStore — one document per workspace (_id)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from application.ports.workspace_embedding_config import WorkspaceEmbeddingConfig

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient


class MongoWorkspaceEmbeddingStore:
    def __init__(
        self,
        client: AsyncIOMotorClient,
        db_name: str,
        collection_name: str = "workspace_embedding_settings",
    ) -> None:
        self._coll = client[db_name][collection_name]

    async def get(self, workspace_id: UUID) -> WorkspaceEmbeddingConfig | None:
        doc = await self._coll.find_one({"_id": str(workspace_id)})
        if doc is None:
            return None
        updated_by = doc.get("updated_by")
        return WorkspaceEmbeddingConfig(
            model=doc["model"],
            updated_by=UUID(updated_by) if updated_by else None,
            updated_at=doc.get("updated_at"),
        )

    async def set(self, workspace_id: UUID, model: str, *, updated_by: UUID) -> None:
        await self._coll.replace_one(
            {"_id": str(workspace_id)},
            {"model": model, "updated_by": str(updated_by), "updated_at": datetime.now(UTC)},
            upsert=True,
        )
