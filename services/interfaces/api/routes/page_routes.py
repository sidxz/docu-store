from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from lagom import Container

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
from application.workflow_use_cases.trigger_compound_extraction_use_case import TriggerCompoundExtractionUseCase
from application.workflow_use_cases.trigger_embedding_use_case import TriggerEmbeddingUseCase
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.workflow_status import WorkflowStatus
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.text_mention import TextMention
from interfaces.api.middleware import handle_use_case_errors
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
@handle_use_case_errors
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
    return await use_case.execute(request=request)


@router.patch("/{page_id}/tag_mentions", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def update_tag_mentions(
    page_id: UUID,
    tag_mentions: list[TagMention],
    container: Annotated[Container, Depends(get_container)],
) -> PageResponse:
    """Update tag mentions for a page."""
    use_case = container[UpdateTagMentionsUseCase]
    return await use_case.execute(page_id=page_id, tag_mentions=tag_mentions)


@router.patch("/{page_id}/text_mention", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def update_text_mention(
    page_id: UUID,
    text_mention: TextMention,
    container: Annotated[Container, Depends(get_container)],
) -> PageResponse:
    """Update text mention for a page."""
    use_case = container[UpdateTextMentionUseCase]
    return await use_case.execute(page_id=page_id, text_mention=text_mention)


@router.patch("/{page_id}/summary_candidate", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def update_summary_candidate(
    page_id: UUID,
    summary_candidate: SummaryCandidate,
    container: Annotated[Container, Depends(get_container)],
) -> PageResponse:
    """Update summary candidate for a page."""
    use_case = container[UpdateSummaryCandidateUseCase]
    return await use_case.execute(page_id=page_id, summary_candidate=summary_candidate)


@router.delete("/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
@handle_use_case_errors
async def delete_page(
    page_id: UUID,
    container: Annotated[Container, Depends(get_container)],
) -> None:
    """Delete a page."""
    use_case = container[DeletePageUseCase]
    return await use_case.execute(page_id=page_id)


@router.post("/{page_id}/compound_mentions", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def update_compound_mentions(
    page_id: UUID,
    request: AddCompoundMentionsRequest,
    container: Annotated[Container, Depends(get_container)],
) -> PageResponse:
    """Add compound_mentions to an existing page."""
    # Validate that the page_id in the path matches the request
    if page_id != request.page_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page ID in path does not match page ID in request body",
        )

    use_case = container[AddCompoundMentionsUseCase]
    return await use_case.execute(request=request)


@router.post("/{page_id}/embeddings/generate", status_code=status.HTTP_202_ACCEPTED)
async def trigger_embedding_generation(
    page_id: UUID,
    container: Annotated[Container, Depends(get_container)],
) -> WorkflowStatus:
    """Trigger embedding generation for a page (non-blocking).

    Starts the embedding Temporal workflow and returns immediately with the
    initial workflow status. Requires the page to have text content.
    """
    use_case = container[TriggerEmbeddingUseCase]
    try:
        return await use_case.execute(page_id=page_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/{page_id}/compounds/extract", status_code=status.HTTP_202_ACCEPTED)
async def trigger_compound_extraction(
    page_id: UUID,
    container: Annotated[Container, Depends(get_container)],
) -> WorkflowStatus:
    """Trigger compound extraction for a page (non-blocking).

    Starts the CSER ML pipeline as a Temporal workflow and returns immediately
    with the initial workflow status. The compounds will be available on the
    page once the workflow completes.
    """
    use_case = container[TriggerCompoundExtractionUseCase]
    try:
        return await use_case.execute(page_id=page_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
