"""MongoDB read model view with tracking support."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from pymongo import MongoClient

if TYPE_CHECKING:
    from eventsourcing.persistence import Tracking
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
        self.tag_dictionary: Collection = self.db[settings.mongo_tag_dictionary_collection]

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
        self.pages.create_index("article_id")  # For filtering tasks by article

        # Artifact collection indexes
        self.artifacts.create_index("artifact_id", unique=True)  # Primary key

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

    def delete_page(
        self,
        page_id: str,
        tracking: Tracking,
    ) -> None:
        """Delete a page read model atomically with tracking."""

        def _delete(session: object) -> None:
            self.pages.delete_one({"page_id": page_id}, session=session)

        self._run_in_transaction(tracking, _delete)
        logger.info(
            "read_model_page_deleted",
            page_id=page_id,
            tracking_id=tracking.notification_id,
        )

    def delete_artifact(
        self,
        artifact_id: str,
        tracking: Tracking,
    ) -> None:
        """Delete an artifact read model atomically with tracking."""

        def _delete(session: object) -> None:
            self.artifacts.delete_one({"artifact_id": artifact_id}, session=session)

        self._run_in_transaction(tracking, _delete)
        logger.info(
            "read_model_artifact_deleted",
            artifact_id=artifact_id,
            tracking_id=tracking.notification_id,
        )

    def replace_artifact_tags(
        self,
        artifact_id: str,
        tags: list[dict[str, str]],
        tracking: Tracking,
    ) -> None:
        """Replace all tag dictionary entries for an artifact."""

        def _handler(session: object) -> None:
            # Look up workspace_id from artifact read model
            artifact = self.artifacts.find_one(
                {"artifact_id": artifact_id},
                {"workspace_id": 1},
                session=session,
            )
            workspace_id = artifact.get("workspace_id") if artifact else None

            # 1. Pull this artifact from tag entries with matching entity_types
            # (scoped so that e.g. author updates don't wipe tag_mentions)
            entity_types_in_batch = list({t["entity_type"] for t in tags}) if tags else []
            if entity_types_in_batch:
                self.tag_dictionary.update_many(
                    {
                        "artifact_ids": artifact_id,
                        "entity_type": {"$in": entity_types_in_batch},
                    },
                    {"$pull": {"artifact_ids": artifact_id}},
                    session=session,
                )
            else:
                # Empty tags = remove this artifact from ALL entries (cleanup)
                self.tag_dictionary.update_many(
                    {"artifact_ids": artifact_id},
                    {"$pull": {"artifact_ids": artifact_id}},
                    session=session,
                )

            # 2. Upsert each tag with $addToSet
            now = datetime.now(UTC)
            for tag_info in tags:
                self.tag_dictionary.update_one(
                    {
                        "workspace_id": workspace_id,
                        "entity_type": tag_info["entity_type"],
                        "tag_normalized": tag_info["tag_normalized"],
                    },
                    {
                        "$addToSet": {"artifact_ids": artifact_id},
                        "$set": {"tag": tag_info["tag"], "last_seen": now},
                        "$setOnInsert": {"workspace_id": workspace_id},
                    },
                    upsert=True,
                    session=session,
                )

            # 3. Recompute artifact_count on affected docs
            recount_filter: dict = {"artifact_ids": artifact_id} if tags else {"workspace_id": workspace_id}
            self.tag_dictionary.update_many(
                recount_filter,
                [{"$set": {"artifact_count": {"$size": {"$ifNull": ["$artifact_ids", []]}}}}],
                session=session,
            )

            # 4. Clean up empty entries
            self.tag_dictionary.delete_many(
                {"artifact_count": 0},
                session=session,
            )

        self._run_in_transaction(tracking, _handler)
        logger.info(
            "tag_dictionary_replaced",
            artifact_id=artifact_id,
            tag_count=len(tags),
            tracking_id=tracking.notification_id,
        )
