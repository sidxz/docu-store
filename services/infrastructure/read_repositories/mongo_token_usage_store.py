"""MongoDB adapter for the TokenUsageStore port."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import structlog
from motor.motor_asyncio import AsyncIOMotorClient

from application.dtos.chat_dtos import TokenUsageDTO
from application.dtos.usage_dtos import KindUsage, MemberTokenUsage, TokenUsageEvent

log = structlog.get_logger(__name__)


def _event_to_doc(event: TokenUsageEvent) -> dict:
    doc: dict = {
        "workspace_id": str(event.workspace_id) if event.workspace_id else None,
        "user_id": str(event.user_id) if event.user_id else None,
        "kind": event.kind,
        "source": event.source,
        "prompt": event.prompt,
        "completion": event.completion,
        "total": event.total,
        "model": event.model,
        "ref": event.ref,
        "created_at": event.created_at,
    }
    if event.event_id:
        doc["_id"] = event.event_id
    return doc


def _rows_to_members(rows: list[dict]) -> list[MemberTokenUsage]:
    """Reshape $group rows keyed by (user_id, kind) into per-member entries."""
    by_user: dict[str | None, MemberTokenUsage] = {}
    for r in rows:
        user_id = r["_id"]["user_id"]
        kind = r["_id"]["kind"]
        member = by_user.setdefault(user_id, MemberTokenUsage(user_id=user_id))
        cell = KindUsage(
            prompt=int(r.get("prompt", 0)),
            completion=int(r.get("completion", 0)),
            total=int(r.get("total", 0)),
            event_count=int(r.get("events", 0)),
        )
        if kind == "ingestion":
            member.ingestion = cell
        else:
            member.chat = cell
        member.total_tokens = member.chat.total + member.ingestion.total
    return sorted(by_user.values(), key=lambda m: m.total_tokens, reverse=True)


class MongoTokenUsageStore:
    """Append-only ledger of LLM token usage events."""

    def __init__(
        self,
        client: AsyncIOMotorClient,
        db_name: str,
        collection_name: str = "token_usage_events",
    ) -> None:
        self._coll = client[db_name][collection_name]

    async def record(self, event: TokenUsageEvent) -> None:
        doc = _event_to_doc(event)
        if "_id" in doc:
            # Deterministic id (live chat writes + backfill) -> idempotent.
            await self._coll.replace_one({"_id": doc["_id"]}, doc, upsert=True)
        else:
            await self._coll.insert_one(doc)

    async def sum_for_user(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        since: datetime | None = None,
        kind: str | None = None,
    ) -> TokenUsageDTO:
        match: dict = {"workspace_id": str(workspace_id), "user_id": str(user_id)}
        if since is not None:
            match["created_at"] = {"$gte": since}
        if kind is not None:
            match["kind"] = kind
        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": None,
                    "prompt": {"$sum": "$prompt"},
                    "completion": {"$sum": "$completion"},
                    "total": {"$sum": "$total"},
                },
            },
        ]
        docs = await self._coll.aggregate(pipeline).to_list(length=1)
        if not docs:
            return TokenUsageDTO(prompt=0, completion=0, total=0)
        d = docs[0]
        return TokenUsageDTO(
            prompt=int(d.get("prompt", 0)),
            completion=int(d.get("completion", 0)),
            total=int(d.get("total", 0)),
        )

    async def usage_by_member(
        self,
        workspace_id: UUID,
        *,
        since: datetime,
    ) -> list[MemberTokenUsage]:
        pipeline = [
            {"$match": {"workspace_id": str(workspace_id), "created_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": {"user_id": "$user_id", "kind": "$kind"},
                    "prompt": {"$sum": "$prompt"},
                    "completion": {"$sum": "$completion"},
                    "total": {"$sum": "$total"},
                    "events": {"$sum": 1},
                },
            },
        ]
        # ponytail: hard 1000-group cap (~500 users/workspace) with no $sort, so an
        # oversized workspace truncates arbitrarily. Add $sort + $limit (top-N by
        # total) if a workspace ever approaches that size.
        rows = await self._coll.aggregate(pipeline).to_list(length=1000)
        return _rows_to_members(rows)

    async def ensure_indexes(self) -> None:
        # ponytail: one compound index; workspace-only admin aggregations prefix-scan
        # it. Add (workspace_id, created_at) if member stats get slow at volume.
        await self._coll.create_index(
            [("workspace_id", 1), ("user_id", 1), ("created_at", -1)],
            name="idx_usage_ws_user_time",
        )
        log.info("usage.ledger.indexes_created")
