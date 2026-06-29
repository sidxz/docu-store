from __future__ import annotations

from typing import TYPE_CHECKING, BinaryIO

import structlog
from returns.result import Failure, Result, Success

from application.dtos.artifact_dtos import CreateArtifactRequest
from application.dtos.errors import AppError
from domain.value_objects.mime_type import MimeType

if TYPE_CHECKING:
    from application.dtos.artifact_dtos import ArtifactResponse
    from application.dtos.blob_dtos import UploadBlobRequest, UploadBlobResponse
    from application.ports.auth import AuthContext
    from application.ports.permission_registrar import PermissionRegistrar
    from application.use_cases.artifact_use_cases import CreateArtifactUseCase
    from application.use_cases.blob_use_cases import UploadBlobUseCase

log = structlog.get_logger(__name__)


class ArtifactUploadSaga:
    """Orchestrates blob upload → artifact creation flow (async parse via Temporal)."""

    def __init__(
        self,
        upload_blob_use_case: UploadBlobUseCase,
        create_artifact_use_case: CreateArtifactUseCase,
        permission_registrar: PermissionRegistrar,
    ) -> None:
        self.upload_blob = upload_blob_use_case
        self.create_artifact = create_artifact_use_case
        self.permission_registrar = permission_registrar

    async def execute(
        self,
        stream: BinaryIO,
        upload_req: UploadBlobRequest,
        auth: AuthContext | None = None,
    ) -> Result[ArtifactResponse, AppError]:
        # Step 1: Upload blob
        blob_result = self.upload_blob.execute(stream, upload_req)
        if isinstance(blob_result, Failure):
            return blob_result

        blob_response: UploadBlobResponse = blob_result.unwrap()

        # Step 2: Create artifact (parse triggered asynchronously via Artifact.Created event)
        create_artifact_request = CreateArtifactRequest(
            artifact_id=blob_response.artifact_id,
            source_uri=blob_response.source_uri,
            source_filename=blob_response.filename,
            artifact_type=upload_req.artifact_type,
            mime_type=MimeType(blob_response.mime_type),
            storage_location=blob_response.storage_key,
        )

        artifact_result = await self.create_artifact.execute(create_artifact_request, auth=auth)
        if isinstance(artifact_result, Failure):
            return artifact_result

        artifact_response = artifact_result.unwrap()

        # Step 3: Register artifact with permission system (best-effort)
        if auth:
            try:
                await self.permission_registrar.register_resource(
                    resource_type="artifact",
                    resource_id=artifact_response.artifact_id,
                    workspace_id=auth.workspace_id,
                    owner_id=auth.user_id,
                    visibility=upload_req.visibility,
                )
            except Exception:
                log.warning(
                    "saga.permission_registration_failed",
                    artifact_id=str(artifact_response.artifact_id),
                    exc_info=True,
                )

        # ponytail: pages intentionally empty — parse workflow fires on Artifact.Created
        return Success(artifact_response)
