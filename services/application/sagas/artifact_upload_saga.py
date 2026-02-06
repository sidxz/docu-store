from typing import BinaryIO

from returns.result import Failure, Result

from application.dtos.artifact_dtos import ArtifactResponse, CreateArtifactRequest
from application.dtos.blob_dtos import UploadBlobRequest, UploadBlobResponse
from application.dtos.errors import AppError
from application.use_cases.artifact_use_cases import CreateArtifactUseCase
from application.use_cases.blob_use_cases import UploadBlobUseCase
from domain.value_objects.mime_type import MimeType


class ArtifactUploadSaga:
    """Orchestrates blob upload → artifact creation flow."""

    def __init__(
        self,
        upload_blob_use_case: UploadBlobUseCase,
        create_artifact_use_case: CreateArtifactUseCase,
    ):
        self.upload_blob = upload_blob_use_case
        self.create_artifact = create_artifact_use_case

    async def execute(
        self,
        stream: BinaryIO,
        upload_req: UploadBlobRequest,
    ) -> Result[ArtifactResponse, AppError]:
        # Step 1: Upload blob
        blob_result = self.upload_blob.execute(stream, upload_req)
        if isinstance(blob_result, Failure):
            return blob_result

        blob_response: UploadBlobResponse = blob_result.unwrap()

        # Step 2: Create artifact from blob response
        create_artifact_request = CreateArtifactRequest(
            artifact_id=blob_response.artifact_id,
            source_uri=blob_response.source_uri,
            source_filename=blob_response.filename,
            artifact_type=upload_req.artifact_type,
            mime_type=MimeType(blob_response.mime_type),
            storage_location=blob_response.storage_key,
        )

        artifact_result = await self.create_artifact.execute(create_artifact_request)
        return artifact_result
