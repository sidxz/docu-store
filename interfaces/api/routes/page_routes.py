from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from lagom import Container
from returns.result import Failure, Success

from application.dtos.page_dtos import AddCompoundMentionsRequest, CreatePageRequest, PageResponse
from application.ports.repositories.page_read_models import PageReadModel
from application.use_cases.page_use_cases import (
    AddCompoundMentionsUseCase,
    CreatePageUseCase,
    DeletePageUseCase,
    UpdateSummaryCandidateUseCase,
    UpdateTagMentionsUseCase,
    UpdateTextMentionUseCase,
)
from domain.exceptions import InfrastructureError
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.text_mention import TextMention
from interfaces.api.routes.helpers import _map_app_error_to_http_exception
from interfaces.dependencies import get_container

router = APIRouter(prefix="/pages", tags=["pages"])


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


@router.patch("/{page_id}/tag_mentions", status_code=status.HTTP_200_OK)
async def update_tag_mentions(
    page_id: UUID,
    tag_mentions: list[TagMention],
    container: Annotated[Container, Depends(get_container)],
) -> PageResponse:
    """Update tag mentions for a page."""
    use_case = container[UpdateTagMentionsUseCase]

    try:
        result = await use_case.execute(page_id=page_id, tag_mentions=tag_mentions)

        if isinstance(result, Success):
            return result.unwrap()

        if isinstance(result, Failure):
            raise _map_app_error_to_http_exception(result.failure()) from None

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected result type",
        ) from None
    except HTTPException:
        raise
    except InfrastructureError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service temporarily unavailable",
        ) from exc
    except BaseException as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc


@router.patch("/{page_id}/text_mention", status_code=status.HTTP_200_OK)
async def update_text_mention(
    page_id: UUID,
    text_mention: TextMention,
    container: Annotated[Container, Depends(get_container)],
) -> PageResponse:
    """Update text mention for a page."""
    use_case = container[UpdateTextMentionUseCase]

    try:
        result = await use_case.execute(page_id=page_id, text_mention=text_mention)

        if isinstance(result, Success):
            return result.unwrap()

        if isinstance(result, Failure):
            raise _map_app_error_to_http_exception(result.failure()) from None

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected result type",
        ) from None
    except HTTPException:
        raise
    except InfrastructureError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service temporarily unavailable",
        ) from exc
    except BaseException as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc


@router.patch("/{page_id}/summary_candidate", status_code=status.HTTP_200_OK)
async def update_summary_candidate(
    page_id: UUID,
    summary_candidate: SummaryCandidate,
    container: Annotated[Container, Depends(get_container)],
) -> PageResponse:
    """Update summary candidate for a page."""
    use_case = container[UpdateSummaryCandidateUseCase]

    try:
        result = await use_case.execute(page_id=page_id, summary_candidate=summary_candidate)

        if isinstance(result, Success):
            return result.unwrap()

        if isinstance(result, Failure):
            raise _map_app_error_to_http_exception(result.failure()) from None

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected result type",
        ) from None
    except HTTPException:
        raise
    except InfrastructureError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service temporarily unavailable",
        ) from exc
    except BaseException as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc


@router.delete("/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page(
    page_id: UUID,
    container: Annotated[Container, Depends(get_container)],
) -> None:
    """Delete a page."""
    use_case = container[DeletePageUseCase]

    try:
        result = await use_case.execute(page_id=page_id)

        if isinstance(result, Success):
            return

        if isinstance(result, Failure):
            raise _map_app_error_to_http_exception(result.failure()) from None

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected result type",
        ) from None
    except HTTPException:
        raise
    except InfrastructureError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service temporarily unavailable",
        ) from exc
    except BaseException as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc


@router.post("/{page_id}/compound_mentions", status_code=status.HTTP_200_OK)
async def update_compound_mentions(
    page_id: UUID,
    request: AddCompoundMentionsRequest,
    container: Annotated[Container, Depends(get_container)],
) -> PageResponse:
    """Add compound_mentions to an existing page.

    Returns:
        200 OK: CompoundMentions successfully added
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

    use_case = container[AddCompoundMentionsUseCase]

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
