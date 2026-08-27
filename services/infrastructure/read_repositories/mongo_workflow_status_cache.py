"""MongoDB adapter for workflow status caching.

Separated from MongoReadRepository because this is a direct CRUD cache,
not an event-sourced read model projection.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, IndexModel, UpdateOne

from application.dtos.workflow_dtos import TemporalWorkflowInfo

logger = structlog.get_logger()

_COLLECTION_NAME = "workflow_status_cache"


class MongoWorkflowStatusCache:
    """Direct CRUD cache for last-known Temporal workflow statuses.

    One document per workflow_id. Upserted on every live Temporal query.
    """

    def __init__(self, client: AsyncIOMotorClient, db_name: str) -> None:
        self._collection = client[db_name][_COLLECTION_NAME]

    async def ensure_indexes(self) -> None:
        await self._collection.create_indexes(
            [
                IndexModel([("workflow_id", ASCENDING)], unique=True),
                IndexModel([("entity_id", ASCENDING), ("entity_type", ASCENDING)]),
            ],
        )

    async def get_cached_statuses(
        self,
        workflow_ids: dict[str, str],
    ) -> dict[str, TemporalWorkflowInfo]:
        wf_id_to_name = {wf_id: name for name, wf_id in workflow_ids.items()}
        cursor = self._collection.find(
            {"workflow_id": {"$in": list(wf_id_to_name.keys())}},
        )
        results: dict[str, TemporalWorkflowInfo] = {}
        async for doc in cursor:
            name = wf_id_to_name.get(doc["workflow_id"])
            if name:
                results[name] = TemporalWorkflowInfo(
                    workflow_id=doc["workflow_id"],
                    status=doc["status"],
                    run_id=doc.get("run_id"),
                    started_at=doc.get("started_at"),
                    closed_at=doc.get("closed_at"),
                    from_cache=True,
                )
        return results

    async def delete_statuses(self, workflow_ids: list[str]) -> None:
        if workflow_ids:
            await self._collection.delete_many({"workflow_id": {"$in": list(workflow_ids)}})

    async def bulk_upsert_statuses(
        self,
        entries: list[tuple[str, str, str, TemporalWorkflowInfo]],
    ) -> None:
        if not entries:
            return
        ops = []
        now = datetime.now(UTC)
        for workflow_name, entity_id, entity_type, info in entries:
            ops.append(
                UpdateOne(
                    {"workflow_id": info.workflow_id},
                    {
                        "$set": {
                            "entity_id": entity_id,
                            "entity_type": entity_type,
                            "workflow_name": workflow_name,
                            "status": info.status,
                            "run_id": info.run_id,
                            "started_at": info.started_at,
                            "closed_at": info.closed_at,
                            "cached_at": now,
                        },
                    },
                    upsert=True,
                ),
            )
        await self._collection.bulk_write(ops, ordered=False)
