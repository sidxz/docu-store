"""MongoDB adapter for user preferences and activity storage.

Separated from MongoReadRepository because these are direct CRUD stores,
not event-sourced read model projections. Different conceptual concern.
"""

from datetime import UTC, datetime
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument

from application.dtos.user_dtos import (
    RecentDocumentEntry,
    SearchHistoryEntry,
    UserPreferencesDTO,
)
from application.ports.repositories.user_activity_store import UserActivityStore
from application.ports.repositories.user_preferences_store import UserPreferencesStore
from infrastructure.config import Settings


class MongoUserStore(UserPreferencesStore, UserActivityStore):
    """Direct CRUD storage for user preferences and activity.

    Not event-sourced. Not a read model projection.
    One document per (workspace_id, user_id) for preferences.
    Append-only + TTL for activity.
    """

    def __init__(self, client: AsyncIOMotorClient, settings: Settings) -> None:
        db = client[settings.mongo_db]
        self.user_preferences = db[settings.mongo_user_preferences_collection]
        self.user_activity = db[settings.mongo_user_activity_collection]

    # ── UserPreferencesStore ─────────────────────────────────────────────────

    async def get_preferences(
        self,
        workspace_id: UUID,
        user_id: UUID,
    ) -> UserPreferencesDTO:
        doc = await self.user_preferences.find_one(
            {
                "workspace_id": str(workspace_id),
                "user_id": str(user_id),
            },
        )
        if not doc:
            return UserPreferencesDTO()
        return UserPreferencesDTO(
            theme=doc.get("theme", "light"),
            sidebar_collapsed=doc.get("sidebar_collapsed", False),
            dev_mode=doc.get("dev_mode", False),
            default_scope=doc.get("default_scope", "workspace"),
            font_family=doc.get("font_family", "plex"),
        )

    async def update_preferences(
        self,
        workspace_id: UUID,
        user_id: UUID,
        updates: dict,
    ) -> UserPreferencesDTO:
        to_set = {**updates, "updated_at": datetime.now(UTC)}
        doc = await self.user_preferences.find_one_and_update(
            {"workspace_id": str(workspace_id), "user_id": str(user_id)},
            {
                "$set": to_set,
                "$setOnInsert": {
                    "workspace_id": str(workspace_id),
                    "user_id": str(user_id),
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return UserPreferencesDTO(
            theme=doc.get("theme", "light"),
            sidebar_collapsed=doc.get("sidebar_collapsed", False),
            dev_mode=doc.get("dev_mode", False),
            default_scope=doc.get("default_scope", "workspace"),
            font_family=doc.get("font_family", "plex"),
        )

    async def ensure_indexes(self) -> None:
        await self.user_preferences.create_indexes(
            [
                IndexModel(
                    [("workspace_id", ASCENDING), ("user_id", ASCENDING)],
                    unique=True,
                ),
            ],
        )
        await self.user_activity.create_indexes(
            [
                IndexModel(
                    [
                        ("workspace_id", ASCENDING),
                        ("user_id", ASCENDING),
                        ("type", ASCENDING),
                        ("created_at", DESCENDING),
                    ],
                ),
                IndexModel(
                    [
                        ("workspace_id", ASCENDING),
                        ("user_id", ASCENDING),
                        ("type", ASCENDING),
                        ("artifact_id", ASCENDING),
                    ],
                ),
                IndexModel(
                    [("created_at", ASCENDING)],
                    expireAfterSeconds=90 * 24 * 60 * 60,  # 90 days TTL
                ),
            ],
        )

    # ── UserActivityStore ────────────────────────────────────────────────────

    async def record_search(
        self,
        workspace_id: UUID,
        user_id: UUID,
        query_text: str,
        search_mode: str,
        result_count: int | None = None,
    ) -> None:
        # Dedup: skip if last search by this user has identical query_text
        last = await self.user_activity.find_one(
            {
                "workspace_id": str(workspace_id),
                "user_id": str(user_id),
                "type": "search",
            },
            sort=[("created_at", DESCENDING)],
        )
        if last and last.get("query_text") == query_text:
            await self.user_activity.update_one(
                {"_id": last["_id"]},
                {"$set": {"created_at": datetime.now(UTC), "result_count": result_count}},
            )
            return

        await self.user_activity.insert_one(
            {
                "workspace_id": str(workspace_id),
                "user_id": str(user_id),
                "type": "search",
                "query_text": query_text,
                "search_mode": search_mode,
                "result_count": result_count,
                "created_at": datetime.now(UTC),
            },
        )

    async def record_document_open(
        self,
        workspace_id: UUID,
        user_id: UUID,
        artifact_id: str,
        artifact_title: str | None = None,
    ) -> None:
        await self.user_activity.update_one(
            {
                "workspace_id": str(workspace_id),
                "user_id": str(user_id),
                "type": "document_open",
                "artifact_id": artifact_id,
            },
            {
                "$set": {
                    "artifact_title": artifact_title,
                    "created_at": datetime.now(UTC),
                },
                "$setOnInsert": {
                    "workspace_id": str(workspace_id),
                    "user_id": str(user_id),
                    "type": "document_open",
                    "artifact_id": artifact_id,
                },
            },
            upsert=True,
        )

    async def get_recent_searches(
        self,
        workspace_id: UUID,
        user_id: UUID,
        limit: int = 20,
    ) -> list[SearchHistoryEntry]:
        cursor = (
            self.user_activity.find(
                {
                    "workspace_id": str(workspace_id),
                    "user_id": str(user_id),
                    "type": "search",
                },
            )
            .sort("created_at", DESCENDING)
            .limit(limit)
        )
        results = []
        async for doc in cursor:
            created = doc["created_at"]
            results.append(
                SearchHistoryEntry(
                    query_text=doc["query_text"],
                    search_mode=doc.get("search_mode", "hierarchical"),
                    result_count=doc.get("result_count"),
                    created_at=created.isoformat()
                    if hasattr(created, "isoformat")
                    else str(created),
                ),
            )
        return results

    async def delete_search_entry(
        self,
        workspace_id: UUID,
        user_id: UUID,
        query_text: str,
    ) -> None:
        await self.user_activity.delete_one(
            {
                "workspace_id": str(workspace_id),
                "user_id": str(user_id),
                "type": "search",
                "query_text": query_text,
            },
        )

    async def clear_search_history(
        self,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        await self.user_activity.delete_many(
            {
                "workspace_id": str(workspace_id),
                "user_id": str(user_id),
                "type": "search",
            },
        )

    async def get_recent_documents(
        self,
        workspace_id: UUID,
        user_id: UUID,
        limit: int = 20,
    ) -> list[RecentDocumentEntry]:
        cursor = (
            self.user_activity.find(
                {
                    "workspace_id": str(workspace_id),
                    "user_id": str(user_id),
                    "type": "document_open",
                },
            )
            .sort("created_at", DESCENDING)
            .limit(limit)
        )
        results = []
        async for doc in cursor:
            created = doc["created_at"]
            results.append(
                RecentDocumentEntry(
                    artifact_id=doc["artifact_id"],
                    artifact_title=doc.get("artifact_title"),
                    created_at=created.isoformat()
                    if hasattr(created, "isoformat")
                    else str(created),
                ),
            )
        return results
