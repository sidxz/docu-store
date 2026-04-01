"""Worker heartbeat reporter.

Each worker process creates a ``HeartbeatReporter`` and runs it alongside
its main loop.  The reporter periodically writes a status document to
MongoDB so that the API health endpoint can aggregate fleet-wide status.

This is a pure **infrastructure** component — it is never referenced from
the application layer and therefore does not need a port.
"""

from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import structlog

from application.dtos.health_dtos import ModelStatus
from infrastructure.health.gpu_info import get_gpu_info, get_system_info

logger = structlog.get_logger()


class HeartbeatReporter:
    """Periodically writes this worker's health snapshot to MongoDB.

    Supports both async workers (``run_forever``) and the synchronous
    read-model projector (``start_sync_background``).  Internally uses
    the **sync** ``pymongo`` driver so a single code-path serves both
    modes — async callers wrap writes with ``asyncio.to_thread``.
    """

    def __init__(
        self,
        *,
        mongo_uri: str,
        mongo_db: str,
        worker_type: str,
        worker_name: str,
        interval_seconds: int = 30,
        model_info_providers: list[Callable[[], Awaitable[ModelStatus]]] | None = None,
    ) -> None:
        self._mongo_uri = mongo_uri
        self._mongo_db = mongo_db
        self._worker_type = worker_type
        self._worker_name = worker_name
        self._interval = interval_seconds
        self._model_providers = model_info_providers or []

        self._hostname = socket.gethostname()
        self._pid = os.getpid()
        self._worker_id = f"{worker_type}:{self._hostname}:{self._pid}"
        self._start_time = time.monotonic()
        self._started_at = datetime.now(tz=UTC)

        # Lazy — created on first write
        self._sync_client = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_forever(self) -> None:
        """Async heartbeat loop.  Run as a background ``asyncio.Task``."""
        logger.info(
            "heartbeat_reporter_started",
            worker_id=self._worker_id,
            interval=self._interval,
        )
        try:
            while True:
                await self._tick()
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            await self.send_shutdown_heartbeat()
            raise

    def start_sync_background(self) -> None:
        """Start a daemon thread that writes heartbeats synchronously.

        Used by the read-model projector which has no asyncio event loop.
        """
        self._stop_event.clear()
        t = threading.Thread(
            target=self._sync_loop,
            name=f"heartbeat-{self._worker_type}",
            daemon=True,
        )
        t.start()
        logger.info(
            "heartbeat_reporter_started_sync",
            worker_id=self._worker_id,
            interval=self._interval,
        )

    def stop(self) -> None:
        """Signal the sync background thread to stop and clean up."""
        self._stop_event.set()
        self._delete_heartbeat_sync()

    async def send_shutdown_heartbeat(self) -> None:
        """Delete this worker's heartbeat on clean shutdown.

        Stale entries from crashed workers are handled by the TTL index
        and the staleness threshold in the reader.
        """
        try:
            await asyncio.to_thread(self._delete_heartbeat_sync)
            logger.info("heartbeat_deleted_on_shutdown", worker_id=self._worker_id)
        except Exception:
            logger.warning("heartbeat_shutdown_failed", worker_id=self._worker_id, exc_info=True)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _tick(self) -> None:
        """Collect info and write one heartbeat."""
        try:
            models = await self._collect_models()
            await asyncio.to_thread(
                self._write_heartbeat_sync,
                models=models,
            )
        except Exception:
            logger.warning("heartbeat_tick_failed", worker_id=self._worker_id, exc_info=True)

    async def _collect_models(self) -> list[ModelStatus]:
        results: list[ModelStatus] = []
        for provider in self._model_providers:
            try:
                results.append(await provider())
            except Exception as exc:
                logger.warning("heartbeat_model_check_failed", error=str(exc))
        return results

    def _sync_loop(self) -> None:
        """Blocking loop for use in a background thread."""
        while not self._stop_event.is_set():
            try:
                self._write_heartbeat_sync()
            except Exception:
                logger.warning("heartbeat_tick_failed", worker_id=self._worker_id, exc_info=True)
            self._stop_event.wait(timeout=self._interval)

    def _write_heartbeat_sync(
        self,
        *,
        models: list[ModelStatus] | None = None,
        offline: bool = False,
    ) -> None:
        """Upsert the heartbeat document using the sync pymongo driver."""
        if self._sync_client is None:
            import pymongo

            self._sync_client = pymongo.MongoClient(self._mongo_uri)

        now = datetime.now(tz=UTC)
        gpu_info = get_gpu_info()
        system_info = get_system_info(self._start_time, now)

        doc = {
            "worker_type": self._worker_type,
            "worker_name": self._worker_name,
            "hostname": self._hostname,
            "pid": self._pid,
            "gpu": gpu_info.model_dump(),
            "loaded_models": [m.model_dump() for m in (models or [])],
            "system": system_info.model_dump(),
            "started_at": self._started_at.isoformat(),
            "last_heartbeat": now.isoformat(),
            # Native datetime for MongoDB TTL index (TTL requires BSON Date)
            "last_heartbeat_dt": now,
            "offline": offline,
        }

        db = self._sync_client[self._mongo_db]
        db.worker_heartbeats.update_one(
            {"_id": self._worker_id},
            {"$set": doc},
            upsert=True,
        )

    def _delete_heartbeat_sync(self) -> None:
        """Remove this worker's heartbeat document on clean shutdown."""
        try:
            if self._sync_client is None:
                import pymongo

                self._sync_client = pymongo.MongoClient(self._mongo_uri)

            db = self._sync_client[self._mongo_db]
            db.worker_heartbeats.delete_one({"_id": self._worker_id})
        except Exception:
            logger.warning("heartbeat_delete_failed", worker_id=self._worker_id, exc_info=True)
