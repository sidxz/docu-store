"""Repository interfaces (ports) for the application layer."""

from abc import ABC, abstractmethod
from uuid import UUID

from domain.aggregates.page import Page


class PageRepository(ABC):
    """Interface for page repository."""

    @abstractmethod
    def save(self, page: Page) -> None:
        """Saves a page entity to the repository."""

    @abstractmethod
    def get_by_id(self, page_id: UUID) -> Page | None:
        """Retrieves a page entity by its ID."""
