"""Protocol for read model materialization with tracking support."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from eventsourcing.persistence import Tracking


class ReadModelMaterializer(Protocol):
    """Protocol defining the interface for materializing read models from events.

    This protocol defines the contract for implementations that synchronize read models
    with event-sourced aggregates, ensuring exactly-once processing of domain events.

    Implementations should provide:
    - ACID transactions for atomic view updates and tracking records
    - Thread-safe notification mechanism for synchronous read-after-write consistency
    - Idempotent event processing using notification tracking
    """

    def upsert_page(
        self,
        page_id: str,
        fields: dict[str, Any],
        tracking: Tracking,
    ) -> None:
        """Upsert a page read model atomically with tracking.

        Args:
            page_id: Unique identifier for the page
            fields: Dictionary of field names to values to update
            tracking: Event tracking information for idempotency

        """
        ...

    def upsert_artifact(
        self,
        artifact_id: str,
        fields: dict[str, Any],
        tracking: Tracking,
    ) -> None:
        """Upsert an artifact read model atomically with tracking.

        Args:
            artifact_id: Unique identifier for the artifact
            fields: Dictionary of field names to values to update
            tracking: Event tracking information for idempotency

        """
        ...

    def delete_page(
        self,
        page_id: str,
        tracking: Tracking,
    ) -> None:
        """Delete a page read model atomically with tracking.

        Args:
            page_id: Unique identifier for the page
            tracking: Event tracking information for idempotency

        """
        ...

    def delete_artifact(
        self,
        artifact_id: str,
        tracking: Tracking,
    ) -> None:
        """Delete an artifact read model atomically with tracking.

        Args:
            artifact_id: Unique identifier for the artifact
            tracking: Event tracking information for idempotency

        """
        ...

    def replace_artifact_tags(
        self,
        artifact_id: str,
        tags: list[dict[str, str]],
        tracking: Tracking,
    ) -> None:
        """Replace all tag dictionary entries for an artifact.

        Atomically: pull artifact_id from all existing entries,
        addToSet artifact_id on each new tag, remove empty entries.
        """
        ...

    def upsert_artifact_and_replace_tags(
        self,
        artifact_id: str,
        fields: dict[str, Any],
        tags: list[dict[str, str]],
        tracking: Tracking,
        *,
        other_entity_types: Sequence[str] | None = None,
    ) -> None:
        """Upsert artifact read model AND replace tag dictionary entries atomically.

        Both operations share a single transaction and tracking record,
        preventing the IntegrityError that occurs when they use separate
        transactions with the same tracking ID. ``other_entity_types``: the write
        owns every entity type except these; without it, only those in ``tags``.
        """
        ...

    def add_to_artifact_array(
        self,
        artifact_id: str,
        field: str,
        values: list[Any],
        tracking: Tracking,
    ) -> None:
        """Add values to an array field on an artifact (no duplicates).

        Args:
            artifact_id: Unique identifier for the artifact
            field: Name of the array field
            values: Values to add
            tracking: Event tracking information for idempotency

        """
        ...

    def pull_from_artifact_array(
        self,
        artifact_id: str,
        field: str,
        values: list[Any],
        tracking: Tracking,
    ) -> None:
        """Remove values from an array field on an artifact.

        Args:
            artifact_id: Unique identifier for the artifact
            field: Name of the array field
            values: Values to remove
            tracking: Event tracking information for idempotency

        """
        ...

    def max_tracking_id(self, application_name: str) -> int | None:
        """Get the highest notification ID processed for an application.

        Args:
            application_name: Name of the application

        Returns:
            The highest notification ID, or None if no events have been processed

        """
        ...
