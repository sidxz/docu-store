from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from returns.result import Failure, Result, Success

from application.dtos.blob_dtos import UploadBlobRequest, UploadBlobResponse
from application.dtos.errors import AppError
from application.ports.blob_store import BlobStore, StoredBlob
from application.ports.external_event_publisher import ExternalEventPublisher
from application.ports.repositories.artifact_repository import ArtifactRepository
from application.ports.repositories.page_repository import PageRepository
from domain.exceptions import ValidationError


class UploadBlobUseCase:
    """Upload a blob and store it."""

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        page_repository: PageRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
        blob_store: BlobStore | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.page_repository = page_repository
        self.external_event_publisher = external_event_publisher
        self.blob_store = blob_store

    def execute(
        self,
        stream: BinaryIO,
        cmd: UploadBlobRequest,
    ) -> Result[UploadBlobResponse, AppError]:
        try:
            artifact_id = uuid4()
            extension = Path(cmd.filename).suffix if cmd.filename else ""
            storage_key = f"artifacts/{artifact_id}/source{extension}"

            stored: StoredBlob = self.blob_store.put_stream(
                storage_key,
                stream,
                mime_type=cmd.mime_type,
            )

            result = UploadBlobResponse(
                storage_key=stored.key,
                sha256=stored.sha256,
                size_bytes=stored.size_bytes,
                mime_type=stored.mime_type,
                filename=cmd.filename,
            )

            return Success(result)
        except ValidationError as e:
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except Exception as e:
            return Failure(AppError("storage_error", f"Failed to upload blob: {e!s}"))
