from uuid import UUID

from eventsourcing.application import Application

from application.ports.repositories.artifact_repository import ArtifactRepository
from domain.aggregates.artifact import Artifact
from domain.exceptions import AggregateNotFoundError, InfrastructureError


def _raise_artifact_not_found(artifact_id: UUID) -> None:
    msg = f"Artifact {artifact_id} not found"
    raise AggregateNotFoundError(msg)


def _raise_artifact_retrieval_error(artifact_id: UUID, exc: Exception) -> None:
    msg = f"Failed to retrieve artifact {artifact_id}: {exc!s}"
    raise InfrastructureError(msg) from exc


class EventSourcedArtifactRepository(ArtifactRepository):
    """Event-sourced implementation of the ArtifactRepository."""

    def __init__(self, application: Application) -> None:
        self.application = application

    def save(self, artifact: Artifact) -> None:
        """Save an artifact entity to the event-sourced repository.

        Raises:
            InfrastructureError: If the event store operation fails.

        """
        try:
            self.application.save(artifact)
        except Exception as e:
            # Let infrastructure errors bubble up for proper error handling at API layer
            msg = f"Failed to save artifact: {e!s}"
            raise InfrastructureError(msg) from e

    def get_by_id(self, artifact_id: UUID) -> Artifact:
        """Retrieve Artifact by rebuilding from event history.

        Raises:
            AggregateNotFoundError: If the artifact does not exist.
            InfrastructureError: If the event store operation fails.

        """
        try:
            artifact = self.application.repository.get(artifact_id)
            if isinstance(artifact, Artifact):
                return artifact
            # This shouldn't happen in normal circumstances
            _raise_artifact_not_found(artifact_id)
        except AggregateNotFoundError:
            # Re-raise our domain exception
            raise
        except Exception as e:
            # Check if it's a 'not found' error from eventsourcing
            error_msg = str(e).lower()
            if "not found" in error_msg or "does not exist" in error_msg:
                msg = f"Artifact {artifact_id} not found"
                raise AggregateNotFoundError(msg) from e
            # Any other exception (network error, DB error, etc.) is an infrastructure error
            _raise_artifact_retrieval_error(artifact_id, e)
