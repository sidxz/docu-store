"""Protocol for read model materialization with tracking support."""

from __future__ import annotations

from typing import Any, Protocol

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

    def max_tracking_id(self, application_name: str) -> int | None:
        """Get the highest notification ID processed for an application.

        Args:
            application_name: Name of the application

        Returns:
            The highest notification ID, or None if no events have been processed

        """
        ...
