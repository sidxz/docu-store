from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from lagom import Container
from returns.result import Failure, Success

from application.dtos.page_dtos import AddCompoundsRequest, CreatePageRequest, PageResponse
from application.use_cases.page_use_cases import AddCompoundsUseCase, CreatePageUseCase
from interfaces.dependencies import get_container

router = APIRouter(prefix="/pages", tags=["pages"])


@router.post("/", response_model=PageResponse, status_code=status.HTTP_201_CREATED)
async def create_page(
    request: CreatePageRequest,
    container: Container = Depends(get_container),
) -> PageResponse:
    """Create a new page."""
    use_case = container[CreatePageUseCase]
    result = use_case.execute(request=request)

    if isinstance(result, Success):
        return result.unwrap()

    if isinstance(result, Failure):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.failure(),
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unexpected result type",
    )


@router.post("/{page_id}/compounds", response_model=PageResponse, status_code=status.HTTP_200_OK)
async def add_compounds(
    page_id: UUID,
    request: AddCompoundsRequest,
    container: Container = Depends(get_container),
) -> PageResponse:
    """Add compounds to an existing page."""
    # Validate that the page_id in the path matches the request
    if page_id != request.page_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page ID in path does not match page ID in request body",
        )

    use_case = container[AddCompoundsUseCase]
    result = use_case.execute(request=request)

    if isinstance(result, Success):
        return result.unwrap()

    if isinstance(result, Failure):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.failure(),
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unexpected result type",
    )
