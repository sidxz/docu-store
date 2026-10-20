from typing import BinaryIO
from uuid import UUID, uuid4

from returns.result import Failure, Result, Success

from application.dtos.blob_dtos import UploadBlobRequest, UploadBlobResponse
from application.dtos.errors import AppError
from application.ports.blob_store import BlobStore, StoredBlob
from application.use_cases.storage_keys import source_key
from application.use_cases.upload_validation import detect_document_type
from domain.exceptions import ValidationError
from domain.value_objects.mime_type import MimeType

# Mirrors the parser registry in di/container.py. Office formats are converted
# to PDF in the async parse workflow; add here as parsers land.
_EXTENSIONS = {MimeType.PDF: ".pdf", MimeType.PPTX: ".pptx", MimeType.DOCX: ".docx"}


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
        workspace_id: UUID,
    ) -> Result[UploadBlobResponse, AppError]:
        try:
            # The bytes decide the type; the client's Content-Type and filename don't.
            mime_type = detect_document_type(stream)

            artifact_id = uuid4()
            storage_key = source_key(workspace_id, artifact_id, _EXTENSIONS[mime_type])

            stored: StoredBlob = self.blob_store.put_stream(
                storage_key,
                stream,
                mime_type=mime_type.value,
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
