"""Repository interfaces (ports) for the application layer."""

from abc import ABC, abstractmethod
from uuid import UUID

from domain.aggregates.artifact import Artifact


class ArtifactRepository(ABC):
    """Interface for artifact repository.

    The repository raises domain exceptions to allow proper error handling
    at the application and interface layers:
    - AggregateNotFoundError: When an aggregate is not found
    - InfrastructureError: When infrastructure operations fail (DB, network, etc.)
    """

    @abstractmethod
    def save(self, artifact: Artifact) -> None:
        """Save artifact entity to the repository.

        Raises:
            InfrastructureError: If the save operation fails.

        """

    @abstractmethod
    def get_by_id(self, artifact_id: UUID) -> Artifact:
        """Retrieve artifact entity by its ID.

        Raises:
            AggregateNotFoundError: If the artifact does not exist.
            InfrastructureError: If the retrieval operation fails.

        """
