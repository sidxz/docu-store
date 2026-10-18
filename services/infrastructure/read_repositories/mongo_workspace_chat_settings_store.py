"""MongoDB adapter for WorkspaceChatSettingsStore — one document per workspace (_id)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from motor.motor_asyncio import AsyncIOMotorClient


class MongoWorkspaceChatSettingsStore:
    def __init__(
        self,
        client: AsyncIOMotorClient,
        db_name: str,
        collection_name: str = "workspace_chat_settings",
    ) -> None:
        self._coll = client[db_name][collection_name]

    async def get_answer_formatting(self, workspace_id: UUID) -> bool | None:
        doc = await self._coll.find_one({"_id": str(workspace_id)}, {"answer_formatting": 1})
        return doc.get("answer_formatting") if doc else None

    async def set_answer_formatting(
        self, workspace_id: UUID, on: bool, *, updated_by: UUID
    ) -> None:
        await self._coll.update_one(
            {"_id": str(workspace_id)},
            {
                "$set": {
                    "answer_formatting": on,
                    "updated_by": str(updated_by),
                    "updated_at": datetime.now(UTC),
                },
            },
            upsert=True,
        )
