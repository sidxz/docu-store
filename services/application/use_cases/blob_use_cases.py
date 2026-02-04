from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

import structlog
from returns.result import Failure, Result, Success

from application.dtos.blob_dtos import (
    UploadBlobRequest,
    UploadBlobResponse,
)
from application.dtos.errors import AppError
from application.ports.blob_store import BlobStore, StoredBlob
from application.ports.external_event_publisher import ExternalEventPublisher
from application.ports.repositories.artifact_repository import ArtifactRepository
from application.ports.repositories.page_repository import PageRepository
from application.ports.workflow_orchestrator import WorkflowOrchestrator
from domain.exceptions import ValidationError

logger = structlog.get_logger()


class UploadBlobUseCase:
    """Upload a blob and store it.

    This use case handles blob uploads and, for PDFs, triggers the PDF ingestion
    workflow as part of the business process.
    """

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        page_repository: PageRepository,
        external_event_publisher: ExternalEventPublisher | None = None,
        blob_store: BlobStore | None = None,
        workflow_orchestrator: WorkflowOrchestrator | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.page_repository = page_repository
        self.external_event_publisher = external_event_publisher
        self.blob_store = blob_store
        self.workflow_orchestrator = workflow_orchestrator

    async def execute(
        self,
        stream: BinaryIO,
        cmd: UploadBlobRequest,
        artifact_id: UUID | None = None,
    ) -> Result[UploadBlobResponse, AppError]:
        """Execute blob upload and trigger processing workflow if applicable.

        Args:
            stream: Binary stream of the blob data
            cmd: Upload request containing filename and mime type
            artifact_id: Optional artifact ID (generated if not provided)

        Returns:
            Result containing upload response or error

        """
        try:
            # Use provided artifact_id or generate new one
            if artifact_id is None:
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

            # Business logic: Trigger PDF ingestion workflow for PDF files
            # This is part of the business process, not infrastructure
            if self.workflow_orchestrator and cmd.mime_type == "application/pdf":
                try:
                    workflow_id = await self.workflow_orchestrator.trigger_pdf_ingestion(
                        storage_key=stored.key,
                        filename=cmd.filename,
                        mime_type=stored.mime_type,
                        source_uri=f"upload://{cmd.filename or 'unknown'}",
                        artifact_id=str(artifact_id),
                    )
                    logger.info(
                        "pdf_ingestion_workflow_triggered",
                        workflow_id=workflow_id,
                        storage_key=stored.key,
                        artifact_id=str(artifact_id),
                    )
                except Exception:
                    # Log but don't fail the upload if workflow trigger fails
                    # The blob is stored successfully, workflow can be retried
                    logger.exception(
                        "workflow_trigger_failed_upload_succeeded",
                        storage_key=stored.key,
                        artifact_id=str(artifact_id),
                    )

            return Success(result)
        except ValidationError as e:
            return Failure(AppError("validation", f"Validation error: {e!s}"))
        except Exception as e:
            return Failure(AppError("storage_error", f"Failed to upload blob: {e!s}"))


class ExtractPdfContentUseCase:
    """Extract content from the first page of a PDF."""

    def __init__(self, blob_store: BlobStore) -> None:
        self.blob_store = blob_store

    def execute(self, storage_key: str, max_words: int = 20) -> Result[str, AppError]:
        """Extract first N words from the first page of a PDF.

        Args:
            storage_key: The storage key of the PDF blob
            max_words: Maximum number of words to extract (default: 20)

        Returns:
            Result containing the extracted text or an error

        """
        try:
            # Import pypdf lazily to avoid loading it if not needed
            from io import BytesIO  # noqa: PLC0415

            from pypdf import PdfReader  # noqa: PLC0415

            # Get the blob content
            blob_bytes = self.blob_store.get_bytes(storage_key)

            # Read PDF and extract text from first page
            reader = PdfReader(BytesIO(blob_bytes))
            if len(reader.pages) == 0:
                return Failure(AppError("validation", "PDF has no pages"))

            first_page = reader.pages[0]
            text = first_page.extract_text()

            if not text:
                return Failure(AppError("extraction_failed", "Could not extract text from PDF"))

            # Extract first N words
            words = text.split()
            extracted_text = " ".join(words[:max_words])

            return Success(extracted_text)
        except Exception as e:  # noqa: BLE001
            # Broad exception needed to catch various PDF parsing errors
            return Failure(AppError("extraction_error", f"Failed to extract PDF content: {e!s}"))
