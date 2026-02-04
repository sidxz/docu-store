from collections.abc import Container
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from returns.result import Failure, Success

from application.dtos.artifact_dtos import ArtifactResponse, CreateArtifactRequest
from application.ports.repositories.artifact_read_models import ArtifactReadModel
from application.use_cases.artifact_use_cases import (
    AddPagesUseCase,
    CreateArtifactUseCase,
    DeleteArtifactUseCase,
    RemovePagesUseCase,
    UpdateSummaryCandidateUseCase,
    UpdateTagsUseCase,
    UpdateTitleMentionUseCase,
)
from domain.exceptions import InfrastructureError
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.title_mention import TitleMention
from interfaces.api.routes.helpers import _map_app_error_to_http_exception
from interfaces.dependencies import get_container

logger = structlog.get_logger()

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("", status_code=status.HTTP_200_OK)
async def list_artifacts(
    container: Annotated[Container, Depends(get_container)],
    skip: Annotated[int, Query(...)] = 0,
    limit: Annotated[int, Query(...)] = 100,
) -> list[ArtifactResponse]:
    """List all artifacts with pagination."""
    read_repository = container[ArtifactReadModel]
    artifacts = await read_repository.list_artifacts(skip=skip, limit=limit)
    return artifacts


@router.get("/{artifact_id}", status_code=status.HTTP_200_OK)
async def get_artifact(
    artifact_id: UUID,
    container: Annotated[Container, Depends(get_container)],
) -> ArtifactResponse:
    """Retrieve an artifact by ID from the read model."""
    read_repository = container[ArtifactReadModel]
    artifact = await read_repository.get_artifact_by_id(artifact_id)

    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found",
        )

    return artifact


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_artifact(
    request: CreateArtifactRequest,
    container: Annotated[Container, Depends(get_container)],
) -> ArtifactResponse:
    """Create a new artifact.

    Returns:
        201 Created: Artifact successfully created
        400 Bad Request: Validation error
        500 Internal Server Error: Infrastructure failure (DB unavailable, etc.)

    """
    use_case = container[CreateArtifactUseCase]

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


@router.post("/{artifact_id}/pages", status_code=status.HTTP_200_OK)
async def add_pages(
    artifact_id: UUID,
    page_ids: list[UUID],
    container: Annotated[Container, Depends(get_container)],
) -> ArtifactResponse:
    """Add pages to an artifact."""
    use_case = container[AddPagesUseCase]

    try:
        result = await use_case.execute(artifact_id=artifact_id, page_ids=page_ids)

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


@router.delete("/{artifact_id}/pages", status_code=status.HTTP_200_OK)
async def remove_pages(
    artifact_id: UUID,
    page_ids: list[UUID],
    container: Annotated[Container, Depends(get_container)],
) -> ArtifactResponse:
    """Remove pages from an artifact."""
    use_case = container[RemovePagesUseCase]

    try:
        result = await use_case.execute(artifact_id=artifact_id, page_ids=page_ids)

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


@router.patch("/{artifact_id}/title_mention", status_code=status.HTTP_200_OK)
async def update_title_mention(
    artifact_id: UUID,
    title_mention: Annotated[TitleMention | None, Body(...)],
    container: Annotated[Container, Depends(get_container)],
) -> ArtifactResponse:
    """Update title mention for an artifact."""
    logger.info(
        "update_title_mention_endpoint_called",
        artifact_id=str(artifact_id),
        title_mention=title_mention,
        title_mention_type=type(title_mention).__name__,
    )
    use_case = container[UpdateTitleMentionUseCase]

    try:
        logger.info(
            "executing_use_case",
            artifact_id=str(artifact_id),
            title_mention=title_mention,
        )
        result = await use_case.execute(artifact_id=artifact_id, title_mention=title_mention)
        logger.info(
            "use_case_result",
            result_type=type(result).__name__,
            is_success=isinstance(result, Success),
        )

        if isinstance(result, Success):
            logger.info("update_title_mention_success")
            return result.unwrap()

        if isinstance(result, Failure):
            logger.warning(
                "update_title_mention_failure",
                failure=str(result.failure()),
            )
            raise _map_app_error_to_http_exception(result.failure()) from None

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected result type",
        ) from None
    except HTTPException:
        raise
    except InfrastructureError as exc:
        logger.error(
            "infrastructure_error_in_update_title_mention",
            error=str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service temporarily unavailable",
        ) from exc
    except BaseException as exc:
        logger.error(
            "unexpected_error_in_update_title_mention",
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc


@router.patch("/{artifact_id}/summary_candidate", status_code=status.HTTP_200_OK)
async def update_summary_candidate(
    artifact_id: UUID,
    summary_candidate: Annotated[SummaryCandidate | None, Body(...)],
    container: Annotated[Container, Depends(get_container)],
) -> ArtifactResponse:
    """Update summary candidate for an artifact."""
    use_case = container[UpdateSummaryCandidateUseCase]

    try:
        result = await use_case.execute(
            artifact_id=artifact_id,
            summary_candidate=summary_candidate,
        )

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


@router.patch("/{artifact_id}/tags", status_code=status.HTTP_200_OK)
async def update_tags(
    artifact_id: UUID,
    tags: Annotated[list[str], Body(...)],
    container: Annotated[Container, Depends(get_container)],
) -> ArtifactResponse:
    """Update tags for an artifact."""
    use_case = container[UpdateTagsUseCase]

    try:
        result = await use_case.execute(artifact_id=artifact_id, tags=tags)

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


@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact(
    artifact_id: UUID,
    container: Annotated[Container, Depends(get_container)],
) -> None:
    """Delete an artifact and all its associated pages."""
    use_case = container[DeleteArtifactUseCase]

    try:
        result = await use_case.execute(artifact_id=artifact_id)

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
