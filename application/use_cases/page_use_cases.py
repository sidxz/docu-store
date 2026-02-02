from returns.result import Failure, Result, Success

from application.dtos.page_dtos import AddCompoundsRequest, CreatePageRequest, PageResponse
from application.ports.repositories.page_repository import PageRepository
from domain.aggregates.page import Page
from domain.exceptions import ValidationError


class CreatePageUseCase:
    def __init__(self, page_repository: PageRepository) -> None:
        self.page_repository = page_repository

    def execute(self, request: CreatePageRequest) -> Result[PageResponse, str]:
        try:
            # Create a new Page aggregate
            page = Page(name=request.name)

            # Save the Page using the repository
            self.page_repository.save(page)

            # Return a successful result with the PageResponse
            return Success(PageResponse(id=page.id, name=page.name, compounds=page.compounds))
        except ValidationError as e:
            return Failure(f"Validation error: {e!s}")
        except Exception as e:
            return Failure(f"Unexpected error: {e!s}")


class AddCompoundsUseCase:
    def __init__(self, page_repository: PageRepository) -> None:
        self.page_repository = page_repository

    def execute(self, request: AddCompoundsRequest) -> Result[PageResponse, str]:
        try:
            # Retrieve the page by ID
            page = self.page_repository.get_by_id(request.page_id)
            if page is None:
                return Failure(f"Page with ID {request.page_id} not found")

            # Add compounds to the page
            page.add_compounds(request.compounds)

            # Save the updated page
            self.page_repository.save(page)

            # Return a successful result with the updated PageResponse
            return Success(PageResponse(id=page.id, name=page.name, compounds=page.compounds))
        except ValidationError as e:
            return Failure(f"Validation error: {e!s}")
        except Exception as e:
            return Failure(f"Unexpected error: {e!s}")
