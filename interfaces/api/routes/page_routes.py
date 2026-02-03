from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from lagom import Container
from returns.result import Failure, Success

from application.dtos.page_dtos import AddCompoundsRequest, CreatePageRequest, PageResponse
from application.ports.repositories.page_read_models import PageReadModel
from application.use_cases.page_use_cases import AddCompoundsUseCase, AppError, CreatePageUseCase
from domain.exceptions import InfrastructureError
from interfaces.dependencies import get_container

router = APIRouter(prefix="/pages", tags=["pages"])


def _map_app_error_to_http_exception(error: AppError) -> HTTPException:
    """Map application layer errors to appropriate HTTP exceptions."""
    if error.category == "validation":
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error.message,
        )
    if error.category == "not_found":
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error.message,
        )
    if error.category == "concurrency":
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error.message,
        )
    # Unknown error category
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error",
    )


@router.get("/{page_id}", status_code=status.HTTP_200_OK)
async def get_page(
    page_id: UUID,
    container: Annotated[Container, Depends(get_container)],
) -> PageResponse:
    """Retrieve a page by ID from the read model."""
    read_repository = container[PageReadModel]
    page = await read_repository.get_page_by_id(page_id)

    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found",
        )

    return page


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_page(
    request: CreatePageRequest,
    container: Annotated[Container, Depends(get_container)],
) -> PageResponse:
    """Create a new page.

    Returns:
        201 Created: Page successfully created
        400 Bad Request: Validation error
        500 Internal Server Error: Infrastructure failure (DB unavailable, etc.)

    """
    use_case = container[CreatePageUseCase]

    try:
        result = await use_case.execute(request=request)

        if isinstance(result, Success):
            return result.unwrap()

        if isinstance(result, Failure):
            raise _map_app_error_to_http_exception(result.failure()) from None

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected result type",
        ) from None
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except InfrastructureError as exc:
        # Infrastructure errors should return 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service temporarily unavailable",
        ) from exc
    except BaseException as exc:
        # Unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc


@router.post("/{page_id}/compounds", status_code=status.HTTP_200_OK)
async def add_compounds(
    page_id: UUID,
    request: AddCompoundsRequest,
    container: Annotated[Container, Depends(get_container)],
) -> PageResponse:
    """Add compounds to an existing page.

    Returns:
        200 OK: Compounds successfully added
        400 Bad Request: Validation error
        404 Not Found: Page not found
        409 Conflict: Page was modified by another request (retry-able)
        500 Internal Server Error: Infrastructure failure (DB unavailable, etc.)

    """
    # Validate that the page_id in the path matches the request
    if page_id != request.page_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page ID in path does not match page ID in request body",
        )

    use_case = container[AddCompoundsUseCase]

    try:
        result = use_case.execute(request=request)

        if isinstance(result, Success):
            return result.unwrap()

        if isinstance(result, Failure):
            raise _map_app_error_to_http_exception(result.failure()) from None

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected result type",
        ) from None
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except InfrastructureError as exc:
        # Infrastructure errors should return 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service temporarily unavailable",
        ) from exc
    except BaseException as exc:
        # Unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc
