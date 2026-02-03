from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from application.dtos.page_dtos import AddCompoundMentionsRequest, CreatePageRequest, PageResponse
from application.mappers.page_mappers import PageMapper
from application.ports.external_event_publisher import ExternalEventPublisher
from application.ports.repositories.page_repository import PageRepository
from domain.aggregates.page import Page
from domain.exceptions import (
    AggregateNotFoundError,
    ConcurrencyError,
    ValidationError,
)


class CreatePageUseCase:
    def __init__(
        self,
        page_repository: PageRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.page_repository = page_repository
        self.external_event_publisher = external_event_publisher

    async def execute(self, request: CreatePageRequest) -> Result[PageResponse, AppError]:
        try:
            # Create a new Page aggregate
            page = Page.create(
                name=request.name,
                artifact_id=request.artifact_id,
                index=request.index,
            )

            # Save the Page using the repository
            self.page_repository.save(page)

            result = PageMapper.to_page_response(page)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_page_created(result)

            # Return a successful result with the PageResponse
            return Success(result)
        except ValidationError as e:
            # Domain validation errors - client's fault (400 Bad Request)
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            # Concurrency conflicts (409 Conflict)
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}"),
            )


class AddCompoundMentionsUseCase:
    def __init__(self, page_repository: PageRepository) -> None:
        self.page_repository = page_repository

    def execute(self, request: AddCompoundMentionsRequest) -> Result[PageResponse, AppError]:
        try:
            # Retrieve the page by ID
            page = self.page_repository.get_by_id(request.page_id)

            # Add compound_mentions to the page
            page.update_compound_mentions(request.compound_mentions)

            # Save the updated page
            self.page_repository.save(page)

            # Return a successful result with the updated PageResponse
            result = PageMapper.to_page_response(page)
            return Success(result)
        except AggregateNotFoundError as e:
            # Page not found - client's fault (404 Not Found)
            return Failure(AppError("not_found", f"Page not found: {e!s}"))
        except ValidationError as e:
            # Domain validation errors - client's fault (400 Bad Request)
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            # Concurrency conflicts (409 Conflict) - retry-able error
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}"),
            )
