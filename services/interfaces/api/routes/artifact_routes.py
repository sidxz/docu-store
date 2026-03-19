from collections.abc import Container
from io import BytesIO
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from returns.result import Success
from sentinel_auth import RequestAuth

from application.dtos.artifact_dtos import ArtifactResponse, CreateArtifactRequest
from application.dtos.blob_dtos import UploadBlobRequest
from application.dtos.permission_dtos import ShareResourceRequest, UpdateVisibilityRequest
from application.dtos.workflow_dtos import WorkflowStartedResponse
from application.ports.blob_store import BlobStore
from application.ports.repositories.artifact_read_models import ArtifactReadModel
from application.ports.workflow_orchestrator import WorkflowOrchestrator
from application.sagas.artifact_upload_saga import ArtifactUploadSaga
from application.use_cases.artifact_use_cases import (
    AddPagesUseCase,
    CreateArtifactUseCase,
    DeleteArtifactUseCase,
    RemovePagesUseCase,
    UpdateSummaryCandidateUseCase,
    UpdateTitleMentionUseCase,
)
from application.use_cases.artifact_use_cases import (
    UpdateTagMentionsUseCase as UpdateArtifactTagMentionsUseCase,
)
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.title_mention import TitleMention
from interfaces.api.middleware import handle_use_case_errors
from interfaces.api.routes.helpers import (
    get_allowed_artifact_ids as _get_allowed_artifact_ids,
)
from interfaces.api.routes.helpers import (
    require_artifact_permission,
    require_workspace_artifact,
)
from interfaces.dependencies import get_auth, get_container

logger = structlog.get_logger()

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("", status_code=status.HTTP_200_OK)
async def list_artifacts(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    skip: Annotated[int, Query(...)] = 0,
    limit: Annotated[int, Query(...)] = 100,
) -> list[ArtifactResponse]:
    """List all artifacts with pagination, filtered by permissions."""
    allowed_artifact_ids = await _get_allowed_artifact_ids(auth)
    read_repository = container[ArtifactReadModel]
    return await read_repository.list_artifacts(
        workspace_id=auth.workspace_id,
        skip=skip,
        limit=limit,
        allowed_artifact_ids=allowed_artifact_ids,
    )


@router.get("/{artifact_id}", status_code=status.HTTP_200_OK)
async def get_artifact(
    artifact_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> ArtifactResponse:
    """Retrieve an artifact by ID from the read model."""
    artifact = await require_workspace_artifact(artifact_id, auth, container)
    await require_artifact_permission(artifact_id, auth, "view")
    return artifact


@router.post("/", status_code=status.HTTP_201_CREATED)
@handle_use_case_errors
async def create_artifact(
    request: CreateArtifactRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> ArtifactResponse:
    """Create a new artifact.

    Returns:
        201 Created: Artifact successfully created
        400 Bad Request: Validation error
        500 Internal Server Error: Infrastructure failure (DB unavailable, etc.)

    """
    use_case = container[CreateArtifactUseCase]
    return await use_case.execute(request=request, auth=auth)


@router.post("/upload", status_code=status.HTTP_201_CREATED)
@handle_use_case_errors
async def upload_blob(  # noqa: PLR0913
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    file: Annotated[UploadFile, File()],
    artifact_type: Annotated[ArtifactType, Form()],
    source_uri: Annotated[str | None, Form()] = None,
    visibility: Annotated[str, Form()] = "workspace",
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
            visibility=visibility,
        ),
        auth=auth,
    )


@router.post("/{artifact_id}/pages", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def add_pages(
    artifact_id: UUID,
    page_ids: list[UUID],
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> ArtifactResponse:
    """Add pages to an artifact."""
    await require_workspace_artifact(artifact_id, auth, container)
    await require_artifact_permission(artifact_id, auth, "edit")
    use_case = container[AddPagesUseCase]
    return await use_case.execute(artifact_id=artifact_id, page_ids=page_ids, auth=auth)


@router.delete("/{artifact_id}/pages", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def remove_pages(
    artifact_id: UUID,
    page_ids: list[UUID],
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> ArtifactResponse:
    """Remove pages from an artifact."""
    await require_workspace_artifact(artifact_id, auth, container)
    await require_artifact_permission(artifact_id, auth, "edit")
    use_case = container[RemovePagesUseCase]
    return await use_case.execute(artifact_id=artifact_id, page_ids=page_ids, auth=auth)


@router.patch("/{artifact_id}/title_mention", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def update_title_mention(
    artifact_id: UUID,
    title_mention: Annotated[TitleMention | None, Body(...)],
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> ArtifactResponse:
    """Update title mention for an artifact."""
    await require_workspace_artifact(artifact_id, auth, container)
    await require_artifact_permission(artifact_id, auth, "edit")
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
    result = await use_case.execute(artifact_id=artifact_id, title_mention=title_mention, auth=auth)
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
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> ArtifactResponse:
    """Update summary candidate for an artifact."""
    await require_workspace_artifact(artifact_id, auth, container)
    await require_artifact_permission(artifact_id, auth, "edit")
    use_case = container[UpdateSummaryCandidateUseCase]
    return await use_case.execute(
        artifact_id=artifact_id,
        summary_candidate=summary_candidate,
        auth=auth,
    )


@router.patch("/{artifact_id}/tag_mentions", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def update_tag_mentions(
    artifact_id: UUID,
    tag_mentions: Annotated[list[TagMention], Body(...)],
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> ArtifactResponse:
    """Update tag mentions for an artifact."""
    await require_workspace_artifact(artifact_id, auth, container)
    await require_artifact_permission(artifact_id, auth, "edit")
    use_case = container[UpdateArtifactTagMentionsUseCase]
    return await use_case.execute(artifact_id=artifact_id, tag_mentions=tag_mentions, auth=auth)


@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
@handle_use_case_errors
async def delete_artifact(
    artifact_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Delete an artifact and all its associated pages."""
    await require_workspace_artifact(artifact_id, auth, container)
    await require_artifact_permission(artifact_id, auth, "edit")
    use_case = container[DeleteArtifactUseCase]
    return await use_case.execute(artifact_id=artifact_id, auth=auth)


@router.post("/{artifact_id}/summarize", status_code=status.HTTP_202_ACCEPTED)
async def trigger_artifact_summarization(
    artifact_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> WorkflowStartedResponse:
    """Trigger LLM summarization for an artifact (non-blocking).

    Starts the sliding-window artifact summarization Temporal workflow and returns
    immediately. The summary is built from all available page-level summaries.

    Unlike the automated pipeline trigger this endpoint skips the "all pages done"
    precondition — useful for re-running after manual corrections or partial ingestion.
    Locked summaries (human corrections) are preserved by the use case.
    """
    await require_workspace_artifact(artifact_id, auth, container)
    await require_artifact_permission(artifact_id, auth, "edit")
    orchestrator = container[WorkflowOrchestrator]
    await orchestrator.start_artifact_summarization_workflow(artifact_id=artifact_id)
    return WorkflowStartedResponse(workflow_id=f"artifact-summarization-{artifact_id}")


@router.post("/{artifact_id}/extract-metadata", status_code=status.HTTP_202_ACCEPTED)
async def trigger_doc_metadata_extraction(
    artifact_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> WorkflowStartedResponse:
    """Trigger document metadata extraction for an artifact (non-blocking).

    Starts the GLiNER2 + LLM extraction workflow for title, authors, and date.
    Uses the first page (index 0) of the artifact. Useful for re-running after
    manual corrections or when automated extraction missed fields.
    """
    artifact = await require_workspace_artifact(artifact_id, auth, container)
    await require_artifact_permission(artifact_id, auth, "edit")

    if not artifact.pages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact has no pages",
        )

    # Pages are resolved to PageResponse objects by the read model
    first_page = artifact.pages[0]
    page_id = first_page.page_id if hasattr(first_page, "page_id") else UUID(str(first_page))

    orchestrator = container[WorkflowOrchestrator]
    await orchestrator.start_doc_metadata_extraction_workflow(
        artifact_id=artifact_id,
        page_id=page_id,
    )
    return WorkflowStartedResponse(workflow_id=f"doc-metadata-{artifact_id}")


@router.get("/{artifact_id}/summary", status_code=status.HTTP_200_OK)
async def get_artifact_summary(
    artifact_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> dict:
    """Get the current summary for an artifact from the read model.

    Returns the summary_candidate field. Returns 404 if the artifact has no
    summary yet.
    """
    artifact = await require_workspace_artifact(artifact_id, auth, container)
    await require_artifact_permission(artifact_id, auth, "view")

    if artifact.summary_candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No summary available for this artifact yet",
        )

    return {
        "artifact_id": str(artifact_id),
        "summary": artifact.summary_candidate.summary,
        "model_name": artifact.summary_candidate.model_name,
        "date_extracted": artifact.summary_candidate.date_extracted,
        "is_locked": artifact.summary_candidate.is_locked,
        "hil_correction": artifact.summary_candidate.hil_correction,
    }


@router.get("/{artifact_id}/workflows", status_code=status.HTTP_200_OK)
async def get_artifact_workflows(
    artifact_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> dict:
    """Get Temporal workflow statuses for an artifact.

    Proxies to Temporal to return the current status of all workflows
    associated with the given artifact.
    """
    await require_workspace_artifact(artifact_id, auth, container)
    await require_artifact_permission(artifact_id, auth, "view")
    orchestrator = container[WorkflowOrchestrator]
    workflows = await orchestrator.get_artifact_workflow_statuses(artifact_id)
    return {"artifact_id": str(artifact_id), "workflows": workflows}


@router.get("/{artifact_id}/pdf", status_code=status.HTTP_200_OK)
async def stream_artifact_pdf(
    artifact_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> StreamingResponse:
    """Stream the source PDF for an artifact.

    Returns the raw PDF binary from blob storage. The artifact must exist
    and have a valid storage_location.
    """
    artifact = await require_workspace_artifact(artifact_id, auth, container)
    await require_artifact_permission(artifact_id, auth, "view")

    blob_store = container[BlobStore]

    if not blob_store.exists(artifact.storage_location):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF file not found in storage",
        )

    pdf_bytes = blob_store.get_bytes(artifact.storage_location)
    filename = artifact.source_filename or f"{artifact_id}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )


@router.get("/{artifact_id}/pages/{page_index}/image", status_code=status.HTTP_200_OK)
async def stream_page_image(
    artifact_id: UUID,
    page_index: int,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> StreamingResponse:
    """Stream the rendered PNG image for a specific page of an artifact.

    Returns the pre-rendered page image from blob storage. Page images
    are generated during PDF ingestion.
    """
    await require_workspace_artifact(artifact_id, auth, container)
    await require_artifact_permission(artifact_id, auth, "view")
    blob_store = container[BlobStore]
    image_key = f"artifacts/{artifact_id}/pages/{page_index}.png"

    if not blob_store.exists(image_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page image not found for index {page_index}",
        )

    image_bytes = blob_store.get_bytes(image_key)

    return StreamingResponse(
        BytesIO(image_bytes),
        media_type="image/png",
    )


# ---------------------------------------------------------------------------
# Entity-level permission endpoints (sharing, visibility)
# ---------------------------------------------------------------------------


@router.get("/{artifact_id}/permissions", status_code=status.HTTP_200_OK)
async def get_artifact_permissions(
    artifact_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> dict:
    """Get the permission ACL for an artifact with user profiles resolved."""
    await require_workspace_artifact(artifact_id, auth, container)
    await require_artifact_permission(artifact_id, auth, "view")
    return await auth.get_enriched_resource_acl("artifact", artifact_id)


@router.post("/{artifact_id}/shares", status_code=status.HTTP_201_CREATED)
async def share_artifact(
    artifact_id: UUID,
    request: ShareResourceRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> dict:
    """Share an artifact with a user or group.

    Only the artifact owner or workspace admin can share.
    Sentinel enforces this server-side; the route also fast-fails.
    """
    artifact = await require_workspace_artifact(artifact_id, auth, container)
    if artifact.owner_id != auth.user_id and not auth.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner or an admin can share this artifact",
        )
    return await auth.share(
        "artifact",
        artifact_id,
        request.grantee_type,
        request.grantee_id,
        request.permission,
    )


@router.delete("/{artifact_id}/shares", status_code=status.HTTP_200_OK)
async def revoke_artifact_share(
    artifact_id: UUID,
    request: ShareResourceRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> dict:
    """Revoke a share on an artifact."""
    artifact = await require_workspace_artifact(artifact_id, auth, container)
    if artifact.owner_id != auth.user_id and not auth.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner or an admin can revoke shares",
        )
    return await auth.unshare(
        "artifact",
        artifact_id,
        request.grantee_type,
        request.grantee_id,
        request.permission,
    )


@router.patch("/{artifact_id}/visibility", status_code=status.HTTP_200_OK)
async def update_artifact_visibility(
    artifact_id: UUID,
    request: UpdateVisibilityRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> dict:
    """Toggle artifact visibility between private and workspace."""
    artifact = await require_workspace_artifact(artifact_id, auth, container)
    if artifact.owner_id != auth.user_id and not auth.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner or an admin can change visibility",
        )
    return await auth.update_visibility("artifact", artifact_id, request.visibility)
