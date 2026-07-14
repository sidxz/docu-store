"""MongoDB adapter for the TokenLimitStore port."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from application.dtos.usage_dtos import TokenLimitEntry

log = structlog.get_logger(__name__)


def _entry_doc(
    workspace_id: UUID,
    user_id: UUID | None,
    limit: int | None,
    updated_by: UUID,
) -> dict:
    return {
        "workspace_id": str(workspace_id),
        "user_id": str(user_id) if user_id else None,
        "limit": limit,
        "updated_at": datetime.now(UTC),
        "updated_by": str(updated_by),
    }


def _doc_to_entry(doc: dict) -> TokenLimitEntry:
    user_id = doc.get("user_id")
    return TokenLimitEntry(
        user_id=UUID(user_id) if user_id else None,
        limit=doc.get("limit"),
    )


class MongoTokenLimitStore:
    """Workspace token limits: per-user override rows + a workspace-default row."""

    def __init__(
        self,
        client: AsyncIOMotorClient,
        db_name: str,
        collection_name: str = "token_limits",
    ) -> None:
        self._coll = client[db_name][collection_name]

    async def get(self, workspace_id: UUID, user_id: UUID | None) -> TokenLimitEntry | None:
        doc = await self._coll.find_one(
            {"workspace_id": str(workspace_id), "user_id": str(user_id) if user_id else None},
        )
        return _doc_to_entry(doc) if doc else None

    async def list_for_workspace(self, workspace_id: UUID) -> list[TokenLimitEntry]:
        # Sort user_id asc: null (the workspace default) sorts first, so the cap
        # can never silently drop it. ponytail: 1000-row cap, page if a workspace
        # ever accumulates that many overrides.
        docs = (
            await self._coll.find({"workspace_id": str(workspace_id)})
            .sort("user_id", 1)
            .to_list(length=1000)
        )
        if len(docs) == 1000:
            log.warning("token_limits.list_truncated", workspace_id=str(workspace_id))
        return [_doc_to_entry(d) for d in docs]

    async def set(
        self,
        workspace_id: UUID,
        user_id: UUID | None,
        limit: int | None,
        updated_by: UUID,
    ) -> None:
        query = {"workspace_id": str(workspace_id), "user_id": str(user_id) if user_id else None}
        doc = _entry_doc(workspace_id, user_id, limit, updated_by)
        try:
            await self._coll.replace_one(query, doc, upsert=True)
        except DuplicateKeyError:
            # Two concurrent first-time upserts raced on the unique index;
            # the row exists now, so the retry takes the replace path.
            await self._coll.replace_one(query, doc, upsert=True)

    async def delete(self, workspace_id: UUID, user_id: UUID) -> None:
        await self._coll.delete_one(
            {"workspace_id": str(workspace_id), "user_id": str(user_id)},
        )

    async def ensure_indexes(self) -> None:
        # Unique also covers the (ws, null) default row — Mongo treats null as a
        # value in unique indexes, so at most one default per workspace.
        await self._coll.create_index(
            [("workspace_id", 1), ("user_id", 1)],
            unique=True,
            name="idx_limits_ws_user",
        )
        log.info("token_limits.indexes_created")
