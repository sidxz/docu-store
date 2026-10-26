"""MongoDB adapter for WorkspaceStorageLimitStore — one document per workspace (_id)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from motor.motor_asyncio import AsyncIOMotorClient


class MongoWorkspaceStorageLimitStore:
    def __init__(
        self,
        client: AsyncIOMotorClient,
        db_name: str,
        collection_name: str = "workspace_storage_limits",
    ) -> None:
        self._coll = client[db_name][collection_name]

    async def get_limit(self, workspace_id: UUID) -> int | None:
        doc = await self._coll.find_one({"_id": str(workspace_id)}, {"limit_bytes": 1})
        return doc.get("limit_bytes") if doc else None

    async def set_limit(
        self, workspace_id: UUID, limit_bytes: int | None, *, updated_by: UUID
    ) -> None:
        await self._coll.update_one(
            {"_id": str(workspace_id)},
            {
                "$set": {
                    "limit_bytes": limit_bytes,
                    "updated_by": str(updated_by),
                    "updated_at": datetime.now(UTC),
                },
            },
            upsert=True,
        )
