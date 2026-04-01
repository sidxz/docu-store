"""MongoDB adapter for reading worker heartbeats.

Implements the ``WorkerHeartbeatStore`` port.  Used by the health checker
to aggregate fleet-wide worker status into the health response.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from application.dtos.health_dtos import (
    GpuInfo,
    ModelStatus,
    SystemInfo,
    WorkerHeartbeat,
)

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient

logger = structlog.get_logger()

_COLLECTION = "worker_heartbeats"

# TTL: auto-delete heartbeats 5 minutes after last update.
# This is intentionally longer than the staleness threshold so that
# recently-dead workers appear as "offline" before vanishing.
_TTL_SECONDS = 300


class MongoHeartbeatReader:
    """Reads worker heartbeats from MongoDB.

    Implements ``application.ports.worker_heartbeat_store.WorkerHeartbeatStore``.
    """

    def __init__(
        self,
        client: AsyncIOMotorClient,
        db_name: str,
        stale_seconds: int,
    ) -> None:
        self._collection = client[db_name][_COLLECTION]
        self._stale_seconds = stale_seconds

    async def ensure_indexes(self) -> None:
        """Create TTL index for automatic cleanup of dead worker heartbeats."""
        try:
            await self._collection.create_index(
                "last_heartbeat_dt",
                expireAfterSeconds=_TTL_SECONDS,
            )
            logger.info("heartbeat_indexes_ensured")
        except Exception:
            logger.warning("heartbeat_index_creation_failed", exc_info=True)

    async def get_all_workers(self) -> list[WorkerHeartbeat]:
        """Return current heartbeats, marking stale ones as offline."""
        now = datetime.now(tz=UTC)
        workers: list[WorkerHeartbeat] = []

        try:
            async for doc in self._collection.find():
                try:
                    workers.append(self._doc_to_heartbeat(doc, now))
                except Exception:
                    logger.warning(
                        "heartbeat_parse_failed",
                        worker_id=doc.get("_id"),
                        exc_info=True,
                    )
        except Exception:
            logger.warning("heartbeat_read_failed", exc_info=True)

        return workers

    def _doc_to_heartbeat(self, doc: dict, now: datetime) -> WorkerHeartbeat:
        last_hb_str = doc["last_heartbeat"]
        last_hb = datetime.fromisoformat(last_hb_str)
        age = (now - last_hb).total_seconds()

        is_offline = doc.get("offline", False) or age > self._stale_seconds

        return WorkerHeartbeat(
            worker_id=doc["_id"],
            worker_type=doc["worker_type"],
            worker_name=doc["worker_name"],
            hostname=doc["hostname"],
            pid=doc["pid"],
            status="offline" if is_offline else "online",
            gpu=GpuInfo(**doc.get("gpu", {"cuda_available": False, "mps_available": False})),
            loaded_models=[ModelStatus(**m) for m in doc.get("loaded_models", [])],
            system=SystemInfo(**doc["system"]),
            started_at=doc["started_at"],
            last_heartbeat=last_hb_str,
        )
