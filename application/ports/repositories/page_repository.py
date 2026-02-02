"""Repository interfaces (ports) for the application layer."""

from abc import ABC, abstractmethod
from uuid import UUID

from domain.aggregates.page import Page


class PageRepository(ABC):
    """Interface for page repository.

    The repository raises domain exceptions to allow proper error handling
    at the application and interface layers:
    - AggregateNotFoundError: When an aggregate is not found
    - InfrastructureError: When infrastructure operations fail (DB, network, etc.)
    """

    @abstractmethod
    def save(self, page: Page) -> None:
        """Saves a page entity to the repository.

        Raises:
            InfrastructureError: If the save operation fails.

        """

    @abstractmethod
    def get_by_id(self, page_id: UUID) -> Page:
        """Retrieves a page entity by its ID.

        Raises:
            AggregateNotFoundError: If the page does not exist.
            InfrastructureError: If the retrieval operation fails.

        """
