from collections.abc import Container
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile, status
from returns.result import Success

from application.dtos.artifact_dtos import ArtifactResponse, CreateArtifactRequest
from application.dtos.blob_dtos import UploadBlobRequest
from application.ports.repositories.artifact_read_models import ArtifactReadModel
from application.ports.workflow_orchestrator import WorkflowOrchestrator
from application.sagas.artifact_upload_saga import ArtifactUploadSaga
from application.use_cases.artifact_use_cases import (
    AddPagesUseCase,
    CreateArtifactUseCase,
    DeleteArtifactUseCase,
    RemovePagesUseCase,
    UpdateSummaryCandidateUseCase,
    UpdateTagsUseCase,
    UpdateTitleMentionUseCase,
)
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.title_mention import TitleMention
from interfaces.api.middleware import handle_use_case_errors
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
    return await read_repository.list_artifacts(skip=skip, limit=limit)


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
@handle_use_case_errors
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
    return await use_case.execute(request=request)


@router.post("/upload", status_code=status.HTTP_201_CREATED)
@handle_use_case_errors
async def upload_blob(
    container: Annotated[Container, Depends(get_container)],
    file: Annotated[UploadFile, File()],
    artifact_type: Annotated[ArtifactType, Form()],
    source_uri: Annotated[str | None, Form()] = None,
) -> ArtifactResponse:
    """Upload a blob to the blob store and create an artifact."""
    saga = container[ArtifactUploadSaga]
    return await saga.execute(
        stream=file.file,
        upload_req=UploadBlobRequest(
            filename=file.filename,
            mime_type=file.content_type,
            artifact_type=artifact_type,
            source_uri=source_uri,
        ),
    )


@router.post("/{artifact_id}/pages", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def add_pages(
    artifact_id: UUID,
    page_ids: list[UUID],
    container: Annotated[Container, Depends(get_container)],
) -> ArtifactResponse:
    """Add pages to an artifact."""
    use_case = container[AddPagesUseCase]
    return await use_case.execute(artifact_id=artifact_id, page_ids=page_ids)


@router.delete("/{artifact_id}/pages", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def remove_pages(
    artifact_id: UUID,
    page_ids: list[UUID],
    container: Annotated[Container, Depends(get_container)],
) -> ArtifactResponse:
    """Remove pages from an artifact."""
    use_case = container[RemovePagesUseCase]
    return await use_case.execute(artifact_id=artifact_id, page_ids=page_ids)


@router.patch("/{artifact_id}/title_mention", status_code=status.HTTP_200_OK)
@handle_use_case_errors
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

    return result


@router.patch("/{artifact_id}/summary_candidate", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def update_summary_candidate(
    artifact_id: UUID,
    summary_candidate: Annotated[SummaryCandidate | None, Body(...)],
    container: Annotated[Container, Depends(get_container)],
) -> ArtifactResponse:
    """Update summary candidate for an artifact."""
    use_case = container[UpdateSummaryCandidateUseCase]
    return await use_case.execute(
        artifact_id=artifact_id,
        summary_candidate=summary_candidate,
    )


@router.patch("/{artifact_id}/tags", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def update_tags(
    artifact_id: UUID,
    tags: Annotated[list[str], Body(...)],
    container: Annotated[Container, Depends(get_container)],
) -> ArtifactResponse:
    """Update tags for an artifact."""
    use_case = container[UpdateTagsUseCase]
    return await use_case.execute(artifact_id=artifact_id, tags=tags)


@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
@handle_use_case_errors
async def delete_artifact(
    artifact_id: UUID,
    container: Annotated[Container, Depends(get_container)],
) -> None:
    """Delete an artifact and all its associated pages."""
    use_case = container[DeleteArtifactUseCase]
    await use_case.execute(artifact_id=artifact_id)


@router.get("/{artifact_id}/workflows", status_code=status.HTTP_200_OK)
async def get_artifact_workflows(
    artifact_id: UUID,
    container: Annotated[Container, Depends(get_container)],
) -> dict:
    """Get Temporal workflow statuses for an artifact.

    Proxies to Temporal to return the current status of all workflows
    associated with the given artifact.
    """
    orchestrator = container[WorkflowOrchestrator]
    workflows = await orchestrator.get_artifact_workflow_statuses(artifact_id)
    return {"artifact_id": str(artifact_id), "workflows": workflows}
