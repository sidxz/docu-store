from __future__ import annotations

from uuid import UUID

from eventsourcing.domain import Aggregate, event

from domain.value_objects.blob_ref import BlobRef


class Blob(Aggregate):
    """Aggregate for a stored blob."""

    INITIAL_VERSION = 0

    @classmethod
    def upload(
        cls,
        *,
        blob_ref: BlobRef,
        source_uri: str,
        artifact_id: UUID | None = None,
        blob_id: UUID | None = None,
    ) -> "Blob":
        if blob_id is None:
            return cls(
                blob_ref=blob_ref,
                source_uri=source_uri,
                artifact_id=artifact_id,
            )
        return cls(
            id=blob_id,
            blob_ref=blob_ref,
            source_uri=source_uri,
            artifact_id=artifact_id,
        )

    class BlobUploaded(Aggregate.Created):
        blob_ref: BlobRef
        source_uri: str
        artifact_id: UUID | None

    @event(BlobUploaded)
    def __init__(
        self,
        blob_ref: BlobRef,
        source_uri: str,
        artifact_id: UUID | None,
    ) -> None:
        source_uri = source_uri.strip()
        if not source_uri:
            msg = "source_uri must be provided"
            raise ValueError(msg)

        self.blob_ref = blob_ref
        self.source_uri = source_uri
        self.artifact_id = artifact_id
