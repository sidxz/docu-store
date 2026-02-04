from __future__ import annotations

from uuid import UUID

from eventsourcing.application import Application

from application.ports.repositories.blob_repository import BlobRepository
from domain.aggregates.blob import Blob
from domain.exceptions import AggregateNotFoundError, InfrastructureError


def _raise_blob_not_found(blob_id: UUID) -> None:
    msg = f"Blob {blob_id} not found"
    raise AggregateNotFoundError(msg)


def _raise_blob_retrieval_error(blob_id: UUID, exc: Exception) -> None:
    msg = f"Failed to retrieve blob {blob_id}: {exc!s}"
    raise InfrastructureError(msg) from exc


class EventSourcedBlobRepository(BlobRepository):
    """Event-sourced implementation of the BlobRepository."""

    def __init__(self, application: Application) -> None:
        self.application = application

    def save(self, blob: Blob) -> None:
        """Save a blob entity to the event-sourced repository."""
        try:
            self.application.save(blob)
        except Exception as e:
            msg = f"Failed to save blob: {e!s}"
            raise InfrastructureError(msg) from e

    def get_by_id(self, blob_id: UUID) -> Blob:
        """Retrieve Blob by rebuilding from event history."""
        try:
            blob = self.application.repository.get(blob_id)
            if isinstance(blob, Blob):
                return blob
            _raise_blob_not_found(blob_id)
        except AggregateNotFoundError:
            raise
        except Exception as e:
            error_msg = str(e).lower()
            if "not found" in error_msg or "does not exist" in error_msg:
                msg = f"Blob {blob_id} not found"
                raise AggregateNotFoundError(msg) from e
            _raise_blob_retrieval_error(blob_id, e)
