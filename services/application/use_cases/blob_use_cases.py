from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from returns.result import Failure, Result, Success

from application.dtos.blob_dtos import UploadBlobRequest, UploadBlobResponse
from application.dtos.errors import AppError
from application.ports.blob_store import BlobStore, StoredBlob
from domain.exceptions import ValidationError
from domain.value_objects.mime_type import MimeType

# ponytail: mirrors the parser registry in di/container.py. Office formats are
# converted to PDF in the async parse workflow; add here as parsers land.
SUPPORTED_UPLOAD_MIME_TYPES = frozenset({MimeType.PDF.value, MimeType.PPTX.value})


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
            # Check MIME type is supported for artifact creation
            if cmd.mime_type not in SUPPORTED_UPLOAD_MIME_TYPES:
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
        except Exception as e:
            # Blob storage implementations can raise various exceptions (IO, network, etc.)
            return Failure(AppError("storage_error", f"Failed to upload blob: {e!s}"))
