"""Base MongoDB read model view with tracking and transactional helpers.

Minimal contract for reuse:
1. Provide MongoDB connectivity inputs (mongo_uri, db_name, tracking_collection_name)
   or pass an already-initialized MongoClient/Database.
2. Override _ensure_view_indexes() to register any view-specific indexes.
3. Use upsert_document() or _run_in_transaction() to apply view updates alongside
   tracking records within a single transaction.
4. Keep read model collections as attributes on the subclass (e.g., self.tasks),
   with the base class only owning the tracking collection.

This module is intentionally framework-agnostic and only depends on pymongo and
eventsourcing.persistence to make extraction into a separate package straightforward.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from threading import Event, Lock
from typing import TYPE_CHECKING, Any

import structlog
from eventsourcing.persistence import IntegrityError, TrackingRecorder
from pymongo import MongoClient

if TYPE_CHECKING:
    from collections.abc import Callable

    from eventsourcing.persistence import Tracking
    from pymongo.client_session import ClientSession
    from pymongo.collection import Collection
    from pymongo.database import Database

logger = structlog.get_logger()


class MongoReadModelTracking(TrackingRecorder):
    """Reusable base class that manages tracking, transactions, and wait helpers."""

    def __init__(
        self,
        *,
        mongo_uri: str,
        db_name: str,
        tracking_collection_name: str,
        client: MongoClient | None = None,
        db: Database | None = None,
    ) -> None:
        self.client = client if client is not None else MongoClient(mongo_uri, tz_aware=True)
        self.db: Database = db if db is not None else self.client[db_name]
        self.tracking: Collection = self.db[tracking_collection_name]

        self._lock = Lock()
        self._events: dict[tuple[str, int], Event] = {}

        self._ensure_indexes()

    # ============================================================================
    # INDEX MANAGEMENT
    # ============================================================================

    def _ensure_indexes(self) -> None:
        """Create tracking + view-specific indexes."""
        try:
            self._ensure_tracking_indexes()
            self._ensure_view_indexes()
        except OSError as exc:  # pragma: no cover - non-critical
            logger.warning("read_model_index_setup_failed", error=str(exc))

    def _ensure_tracking_indexes(self) -> None:
        """Create tracking indexes needed for idempotency."""
        self.tracking.create_index(
            [("application_name", 1), ("notification_id", 1)],
            unique=True,
        )

    def _ensure_view_indexes(self) -> None:
        """Register read-model-specific indexes in subclasses."""

    # ============================================================================
    # TRANSACTION HELPERS
    # ============================================================================

    def _run_in_transaction(
        self,
        tracking: Tracking,
        handler: Callable[[ClientSession], None],
    ) -> None:
        with self.client.start_session() as session, session.start_transaction():
            self._assert_tracking_uniqueness(tracking, session)
            handler(session)
            self._insert_tracking(tracking, session)

    def upsert_document(
        self,
        *,
        collection: Collection,
        identity_field: str,
        identity_value: str,
        fields: dict[str, Any],
        tracking: Tracking,
    ) -> None:
        """Upsert a document and record the tracking atomically."""
        fields[identity_field] = identity_value
        fields["updated_at"] = datetime.now(UTC)

        def _upsert(session: ClientSession) -> None:
            collection.update_one(
                {identity_field: identity_value},
                {"$set": fields},
                upsert=True,
                session=session,
            )

        self._run_in_transaction(tracking, _upsert)

    # ============================================================================
    # TRACKING AND IDEMPOTENCY
    # ============================================================================

    def _assert_tracking_uniqueness(
        self,
        tracking: Tracking,
        session: ClientSession,
    ) -> None:
        query = {
            "application_name": tracking.application_name,
            "notification_id": tracking.notification_id,
        }
        existing = self.tracking.find_one(query, session=session)

        if existing:
            msg = f"Tracking already exists: {tracking.application_name}:{tracking.notification_id}"
            raise IntegrityError(msg)

    def _insert_tracking(self, tracking: Tracking, session: ClientSession) -> None:
        doc = {
            "application_name": tracking.application_name,
            "notification_id": tracking.notification_id,
            "recorded_at": datetime.now(UTC),
        }
        self.tracking.insert_one(doc, session=session)
        self._signal_position(tracking.application_name, tracking.notification_id)

    def insert_tracking(self, tracking: Tracking) -> None:
        with self.client.start_session() as session, session.start_transaction():
            self._insert_tracking(tracking, session)

    # ============================================================================
    # CHECKPOINT QUERIES
    # ============================================================================

    def max_tracking_id(self, application_name: str) -> int | None:
        doc = self.tracking.find_one(
            {"application_name": application_name},
            sort=[("notification_id", -1)],
        )
        if not doc:
            return None
        return int(doc["notification_id"])

    # ============================================================================
    # SYNCHRONOUS READ-AFTER-WRITE
    # ============================================================================

    def wait(
        self,
        application_name: str,
        notification_id: int,
        timeout: float = 30.0,
    ) -> None:
        start = time.time()
        while time.time() - start < timeout:
            current_max = self.max_tracking_id(application_name)
            if current_max is not None and current_max >= notification_id:
                return

            key = (application_name, notification_id)
            with self._lock:
                if key not in self._events:
                    self._events[key] = Event()
                event = self._events[key]

            remaining = timeout - (time.time() - start)
            if remaining <= 0:
                break
            event.wait(timeout=min(remaining, 0.1))

        current_max = self.max_tracking_id(application_name)
        if current_max is None or current_max < notification_id:
            msg = f"Timeout waiting for {application_name}:{notification_id}"
            raise TimeoutError(msg)

    def _signal_position(self, application_name: str, notification_id: int) -> None:
        with self._lock:
            keys_to_remove = []
            for key, event in list(self._events.items()):
                app_name, notif_id = key
                if app_name == application_name and notif_id <= notification_id:
                    event.set()
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                self._events.pop(key, None)
