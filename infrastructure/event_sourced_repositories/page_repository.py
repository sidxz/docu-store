from uuid import UUID

from eventsourcing.application import Application

from application.ports.repositories.page_repository import PageRepository
from domain.aggregates.page import Page
from domain.exceptions import AggregateNotFoundError, InfrastructureError


def _raise_page_not_found(page_id: UUID) -> None:
    msg = f"Page {page_id} not found"
    raise AggregateNotFoundError(msg)


def _raise_page_retrieval_error(page_id: UUID, exc: Exception) -> None:
    msg = f"Failed to retrieve page {page_id}: {exc!s}"
    raise InfrastructureError(msg) from exc


class EventSourcedPageRepository(PageRepository):
    """Event-sourced implementation of the PageRepository."""

    def __init__(self, application: Application) -> None:
        self.application = application

    def save(self, page: Page) -> None:
        """Save a page entity to the event-sourced repository.

        Raises:
            InfrastructureError: If the event store operation fails.

        """
        try:
            self.application.save(page)
        except Exception as e:
            # Let infrastructure errors bubble up for proper error handling at API layer
            msg = f"Failed to save page: {e!s}"
            raise InfrastructureError(msg) from e

    def get_by_id(self, page_id: UUID) -> Page:
        """Retrieve Page by rebuilding from event history.

        Raises:
            AggregateNotFoundError: If the page does not exist.
            InfrastructureError: If the event store operation fails.

        """
        try:
            page = self.application.repository.get(page_id)
            if isinstance(page, Page):
                return page
            # This shouldn't happen in normal circumstances
            _raise_page_not_found(page_id)
        except AggregateNotFoundError:
            # Re-raise our domain exception
            raise
        except Exception as e:
            # Check if it's a 'not found' error from eventsourcing
            error_msg = str(e).lower()
            if "not found" in error_msg or "does not exist" in error_msg:
                msg = f"Page {page_id} not found"
                raise AggregateNotFoundError(msg) from e
            # Any other exception (network error, DB error, etc.) is an infrastructure error
            _raise_page_retrieval_error(page_id, e)
