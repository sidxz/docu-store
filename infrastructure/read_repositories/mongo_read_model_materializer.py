"""MongoDB read model view with tracking support."""

from __future__ import annotations

from typing import Any

import structlog
from eventsourcing.persistence import Tracking
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from infrastructure.config import settings
from infrastructure.lib.mongo_read_model_tracking import MongoReadModelTracking

logger = structlog.get_logger()


class MongoReadModelMaterializer(MongoReadModelTracking):
    """MongoDB materialized view for read models using replica set transactions.

    This class provides a materialized view layer that synchronizes read models with
    event-sourced aggregates. It implements the TrackingRecorder interface to ensure
    exactly-once processing of domain events.

    Key Features:
    - ACID transactions for atomic view updates and tracking records
    - Thread-safe notification mechanism for synchronous read-after-write consistency
    - Idempotent event processing using notification tracking
    - Separate collections for pages, articles, and processing checkpoints

    Thread Safety:
    Uses locks and events to coordinate between producer (event processor) threads
    and consumer (API) threads waiting for specific updates to be materialized.
    """

    def __init__(self) -> None:
        # Initialize synchronous MongoDB client with timezone awareness
        self.client = MongoClient(settings.mongo_uri, tz_aware=True)
        self.db: Database = self.client[settings.mongo_db]

        # Main read model collections
        self.pages: Collection = self.db[settings.mongo_pages_collection]
        self.artifacts: Collection = self.db[settings.mongo_artifacts_collection]

        super().__init__(
            mongo_uri=settings.mongo_uri,
            db_name=settings.mongo_db,
            tracking_collection_name=settings.mongo_tracking_collection,
            client=self.client,
            db=self.db,
        )

    # ============================================================================
    # INDEX MANAGEMENT
    # ============================================================================

    def _ensure_view_indexes(self) -> None:
        """Create page/article indexes for performance and data integrity."""
        # Page collection indexes
        self.pages.create_index("page_id", unique=True)  # Primary key
        # self.pages.create_index("article_id")  # For filtering tasks by article
        # self.pages.create_index("status")  # For filtering by task status

        # Artifact collection indexes
        self.artifacts.create_index("artifact_id", unique=True)  # Primary key
        # self.artifacts.create_index("artifact_type")  # For filtering by type
        # self.artifacts.create_index("status")  # For filtering by artifact status

    # ============================================================================
    # ATOMIC UPSERT OPERATIONS
    # These methods update read models and record tracking in a single transaction
    # ============================================================================

    def upsert_page(
        self,
        page_id: str,
        fields: dict[str, Any],
        tracking: Tracking,
    ) -> None:
        self.upsert_document(
            collection=self.pages,
            identity_field="page_id",
            identity_value=page_id,
            fields=fields,
            tracking=tracking,
        )
        logger.info(
            "read_model_page_upserted",
            page_id=page_id,
            tracking_id=tracking.notification_id,
        )

    def upsert_artifact(
        self,
        artifact_id: str,
        fields: dict[str, Any],
        tracking: Tracking,
    ) -> None:
        self.upsert_document(
            collection=self.artifacts,
            identity_field="artifact_id",
            identity_value=artifact_id,
            fields=fields,
            tracking=tracking,
        )
        logger.info(
            "read_model_artifact_upserted",
            artifact_id=artifact_id,
            tracking_id=tracking.notification_id,
        )
