"""Temporal activities for PDF processing workflows.

These activities are infrastructure layer components that call application use cases.
They are idempotent and follow Temporal best practices for activity implementation.
"""

from dataclasses import dataclass

import structlog
from temporalio import activity

from application.dtos.artifact_dtos import CreateArtifactRequest
from application.use_cases.artifact_use_cases import CreateArtifactWithTitleUseCase
from application.use_cases.blob_use_cases import ExtractPdfContentUseCase
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType

logger = structlog.get_logger()


@dataclass
class PdfProcessingInput:
    """Input data for PDF processing workflow."""

    artifact_id: str
    storage_key: str
    filename: str | None
    source_uri: str


@dataclass
class ExtractedContent:
    """Output from PDF content extraction."""

    text: str
    word_count: int


class PdfProcessingActivities:
    """Activities for PDF processing workflows.

    These activities call application use cases to perform business logic,
    maintaining separation between infrastructure (Temporal) and application layers.
    """

    def __init__(
        self,
        extract_pdf_content_use_case: ExtractPdfContentUseCase,
        create_artifact_with_title_use_case: CreateArtifactWithTitleUseCase,
    ) -> None:
        self.extract_pdf_content_use_case = extract_pdf_content_use_case
        self.create_artifact_with_title_use_case = create_artifact_with_title_use_case

    @activity.defn(name="check_if_pdf")
    async def check_if_pdf(self, filename: str | None, mime_type: str | None) -> bool:
        """Check if the uploaded file is a PDF.

        Args:
            filename: Name of the uploaded file
            mime_type: MIME type of the uploaded file

        Returns:
            True if file is a PDF, False otherwise

        """
        activity.logger.info("Checking if file is PDF", filename=filename, mime_type=mime_type)

        # Check by MIME type first
        if mime_type and "pdf" in mime_type.lower():
            activity.logger.info("File is PDF (by MIME type)")
            return True

        # Check by file extension
        if filename and filename.lower().endswith(".pdf"):
            activity.logger.info("File is PDF (by extension)")
            return True

        activity.logger.info("File is not a PDF")
        return False

    @activity.defn(name="extract_pdf_first_page_content")
    async def extract_pdf_first_page_content(
        self,
        storage_key: str,
        max_words: int = 20,
    ) -> ExtractedContent:
        """Extract first N words from the first page of a PDF.

        Args:
            storage_key: Storage key of the PDF blob
            max_words: Maximum number of words to extract (default: 20)

        Returns:
            ExtractedContent with text and word count

        Raises:
            RuntimeError: If extraction fails

        """
        activity.logger.info(
            "Extracting PDF content",
            storage_key=storage_key,
            max_words=max_words,
        )

        result = self.extract_pdf_content_use_case.execute(storage_key, max_words)

        if result.is_success():
            text = result.unwrap()
            word_count = len(text.split())
            activity.logger.info(
                "PDF content extracted successfully",
                word_count=word_count,
            )
            return ExtractedContent(text=text, word_count=word_count)

        error = result.failure()
        activity.logger.error(
            "PDF content extraction failed",
            error_type=error.error_type,
            message=error.message,
        )
        msg = f"Failed to extract PDF content: {error.message}"
        raise RuntimeError(msg)

    @activity.defn(name="create_artifact_with_title")
    async def create_artifact_with_title(
        self,
        artifact_id: str,
        storage_key: str,
        filename: str | None,
        source_uri: str,
        title_text: str,
    ) -> str:
        """Create an artifact and set its title.

        Args:
            artifact_id: UUID of the artifact to create
            storage_key: Storage location of the blob
            filename: Original filename
            source_uri: Source URI of the document
            title_text: Text to use as title

        Returns:
            Artifact ID as string

        Raises:
            RuntimeError: If artifact creation fails

        """
        activity.logger.info(
            "Creating artifact with title",
            artifact_id=artifact_id,
            title_text=title_text,
        )

        # Create the request
        request = CreateArtifactRequest(
            source_uri=source_uri,
            source_filename=filename or "unknown.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location=storage_key,
        )

        # Call the use case
        result = await self.create_artifact_with_title_use_case.execute(request, title_text)

        if result.is_success():
            artifact_response = result.unwrap()
            activity.logger.info(
                "Artifact created successfully",
                artifact_id=str(artifact_response.artifact_id),
            )
            return str(artifact_response.artifact_id)

        error = result.failure()
        activity.logger.error(
            "Artifact creation failed",
            error_type=error.error_type,
            message=error.message,
        )
        msg = f"Failed to create artifact: {error.message}"
        raise RuntimeError(msg)
