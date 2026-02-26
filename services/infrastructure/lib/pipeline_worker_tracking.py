"""Lightweight checkpoint store for the pipeline worker.

Stores a single high-water mark position per worker name so the worker can
resume from where it left off after a crash or restart, independently of the
read model projector's tracking.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from pymongo import MongoClient

from infrastructure.config import settings

logger = structlog.get_logger()

_COLLECTION = "pipeline_worker_tracking"


class PipelineWorkerTracking:
    """Stores and retrieves the last-processed event position for a named worker.

    Uses a simple upsert — one document per worker name — rather than the
    per-event records used by the read model materializer. Temporal workflow IDs
    already guarantee idempotency for the actual work, so a checkpoint is enough.
    """

    def __init__(self, worker_name: str) -> None:
        self._worker_name = worker_name
        client = MongoClient(settings.mongo_uri, tz_aware=True)
        db = client[settings.mongo_db]
        self._col = db[_COLLECTION]
        self._col.create_index("worker_name", unique=True)

    def get_position(self) -> int | None:
        """Return the last saved position, or None to start from the beginning."""
        doc = self._col.find_one({"worker_name": self._worker_name})
        if not doc:
            return None
        return int(doc["position"])

    def save_position(self, notification_id: int) -> None:
        """Advance the checkpoint to notification_id."""
        self._col.update_one(
            {"worker_name": self._worker_name},
            {"$set": {"position": notification_id, "updated_at": datetime.now(UTC)}},
            upsert=True,
        )
