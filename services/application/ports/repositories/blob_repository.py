from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from domain.aggregates.blob import Blob


class BlobRepository(ABC):
    """Port for blob aggregate persistence."""

    @abstractmethod
    def save(self, blob: Blob) -> None:
        """Persist a blob aggregate."""

    @abstractmethod
    def get_by_id(self, blob_id: UUID) -> Blob:
        """Retrieve a blob aggregate by ID."""
