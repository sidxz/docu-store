from uuid import UUID

from eventsourcing.application import Application

from application.ports.repositories.page_repository import PageRepository
from domain.aggregates.page import Page


class EventSourcedPageRepository(PageRepository):
    """Event-sourced implementation of the PageRepository."""

    def __init__(self, application: Application) -> None:
        self.application = application

    def save(self, page: Page) -> None:
        """Save a page entity to the event-sourced repository."""
        self.application.save(page)

    def get_by_id(self, page_id: UUID) -> Page | None:
        """Retrieve Page by rebuilding from event history."""
        try:
            page = self.application.repository.get(page_id)
            if isinstance(page, Page):
                return page
            return None
        except Exception:
            return None
