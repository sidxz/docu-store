from returns.result import Failure, Result, Success

from application.dtos.page_dtos import AddCompoundsRequest, CreatePageRequest, PageResponse
from application.ports.repositories.page_repository import PageRepository
from domain.aggregates.page import Page
from domain.exceptions import (
    AggregateNotFoundError,
    ConcurrencyError,
    ValidationError,
)


class AppError:
    """Represents different categories of application errors."""

    def __init__(self, category: str, message: str) -> None:
        self.category = category  # 'validation', 'not_found', 'concurrency', 'infrastructure'
        self.message = message

    def __str__(self) -> str:
        return self.message


class CreatePageUseCase:
    def __init__(self, page_repository: PageRepository) -> None:
        self.page_repository = page_repository

    def execute(self, request: CreatePageRequest) -> Result[PageResponse, AppError]:
        try:
            # Create a new Page aggregate
            page = Page.create(name=request.name)

            # Save the Page using the repository
            self.page_repository.save(page)

            # Return a successful result with the PageResponse
            return Success(PageResponse(page_id=page.id, name=page.name, compounds=page.compounds))
        except ValidationError as e:
            # Domain validation errors - client's fault (400 Bad Request)
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            # Concurrency conflicts (409 Conflict)
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}")
            )


class AddCompoundsUseCase:
    def __init__(self, page_repository: PageRepository) -> None:
        self.page_repository = page_repository

    def execute(self, request: AddCompoundsRequest) -> Result[PageResponse, AppError]:
        try:
            # Retrieve the page by ID
            page = self.page_repository.get_by_id(request.page_id)

            # Add compounds to the page
            page.add_compounds(request.compounds)

            # Save the updated page
            self.page_repository.save(page)

            # Return a successful result with the updated PageResponse
            return Success(PageResponse(page_id=page.id, name=page.name, compounds=page.compounds))
        except AggregateNotFoundError as e:
            # Page not found - client's fault (404 Not Found)
            return Failure(AppError("not_found", f"Page not found: {e!s}"))
        except ValidationError as e:
            # Domain validation errors - client's fault (400 Bad Request)
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except ConcurrencyError as e:
            # Concurrency conflicts (409 Conflict) - retry-able error
            return Failure(
                AppError("concurrency", f"Resource was modified by another request: {e!s}")
            )
