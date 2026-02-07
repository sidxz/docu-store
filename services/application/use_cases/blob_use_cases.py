from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from returns.result import Failure, Result, Success

from application.dtos.blob_dtos import UploadBlobRequest, UploadBlobResponse
from application.dtos.errors import AppError
from application.ports.blob_store import BlobStore, StoredBlob
from domain.exceptions import ValidationError
from domain.value_objects.mime_type import MimeType


class UploadBlobUseCase:
    """Upload a blob and store it."""

    def __init__(
        self,
        blob_store: BlobStore | None = None,
    ) -> None:
        self.blob_store = blob_store

    def execute(
        self,
        stream: BinaryIO,
        cmd: UploadBlobRequest,
    ) -> Result[UploadBlobResponse, AppError]:
        try:
            # Check MIME type is supported for artifact creation Only PDFs for now
            if cmd.mime_type != MimeType.PDF.value:
                return Failure(
                    AppError(
                        "validation",
                        f"Unsupported MIME type for artifact creation: {cmd.mime_type}",
                    ),
                )

            artifact_id = uuid4()
            extension = Path(cmd.filename).suffix if cmd.filename else ""
            storage_key = f"artifacts/{artifact_id}/source{extension}"

            stored: StoredBlob = self.blob_store.put_stream(
                storage_key,
                stream,
                mime_type=cmd.mime_type,
            )

            result = UploadBlobResponse(
                artifact_id=artifact_id,
                storage_key=stored.key,
                sha256=stored.sha256,
                size_bytes=stored.size_bytes,
                mime_type=stored.mime_type,
                filename=cmd.filename,
                source_uri=cmd.source_uri,
            )

            return Success(result)
        except ValidationError as e:
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except Exception as e:  # noqa: BLE001
            # Blob storage implementations can raise various exceptions (IO, network, etc.)
            return Failure(AppError("storage_error", f"Failed to upload blob: {e!s}"))
