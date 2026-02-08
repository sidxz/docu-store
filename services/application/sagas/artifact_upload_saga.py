from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, BinaryIO

from returns.result import Failure, Result, Success

from application.dtos.artifact_dtos import CreateArtifactRequest
from application.dtos.errors import AppError
from application.dtos.page_dtos import CreatePageRequest
from domain.exceptions import InfrastructureError, ValidationError
from domain.value_objects.mime_type import MimeType
from domain.value_objects.text_mention import TextMention

if TYPE_CHECKING:
    from application.dtos.artifact_dtos import ArtifactResponse
    from application.dtos.blob_dtos import UploadBlobRequest, UploadBlobResponse
    from application.dtos.pdf_dtos import PDFContent
    from application.ports.pdf_service import PDFService
    from application.use_cases.artifact_use_cases import (
        AddPagesUseCase,
        CreateArtifactUseCase,
    )
    from application.use_cases.blob_use_cases import UploadBlobUseCase
    from application.use_cases.page_use_cases import (
        CreatePageUseCase,
        UpdateTextMentionUseCase,
    )


class ArtifactUploadSaga:
    """Orchestrates blob upload → artifact creation flow."""

    def __init__(  # noqa: PLR0913
        self,
        upload_blob_use_case: UploadBlobUseCase,
        create_artifact_use_case: CreateArtifactUseCase,
        create_page_use_case: CreatePageUseCase,
        add_pages_use_case: AddPagesUseCase,
        update_text_mention_use_case: UpdateTextMentionUseCase,
        pdf_service: PDFService,
    ) -> None:
        """Initialize saga with required use cases and services.

        Args:
            upload_blob_use_case: Use case for uploading blobs
            create_artifact_use_case: Use case for creating artifacts
            create_page_use_case: Use case for creating pages
            add_pages_use_case: Use case for adding pages to artifacts
            update_text_mention_use_case: Use case for updating text mentions
            pdf_service: Service for parsing PDFs

        """
        self.upload_blob = upload_blob_use_case
        self.create_artifact = create_artifact_use_case
        self.create_page = create_page_use_case
        self.add_pages = add_pages_use_case
        self.update_text_mention = update_text_mention_use_case
        self.pdf_service = pdf_service

    async def execute(
        self,
        stream: BinaryIO,
        upload_req: UploadBlobRequest,
    ) -> Result[ArtifactResponse, AppError]:
        now = datetime.now(tz=UTC)
        # Step 1: Upload blob
        blob_result = self.upload_blob.execute(stream, upload_req)
        if isinstance(blob_result, Failure):
            return blob_result

        blob_response: UploadBlobResponse = blob_result.unwrap()

        # Step 2: Parse PDF to extract pages
        try:
            pdf_content: PDFContent = self.pdf_service.parse(storage_key=blob_response.storage_key)
        except ValidationError as e:
            return Failure(AppError("validation", f"PDF validation error: {e!s}"))
        except InfrastructureError as e:
            return Failure(AppError("infrastructure", f"Failed to parse PDF: {e!s}"))

        # Step 3: Create artifact from blob response
        create_artifact_request = CreateArtifactRequest(
            artifact_id=blob_response.artifact_id,
            source_uri=blob_response.source_uri,
            source_filename=blob_response.filename,
            artifact_type=upload_req.artifact_type,
            mime_type=MimeType(blob_response.mime_type),
            storage_location=blob_response.storage_key,
        )

        artifact_result = await self.create_artifact.execute(create_artifact_request)
        if isinstance(artifact_result, Failure):
            return artifact_result

        artifact_response = artifact_result.unwrap()
        artifact_id = artifact_response.artifact_id

        # Step 4 : Create pages and add to artifact
        pages_result = await self._process_pdf_pages(
            pdf_content=pdf_content,
            artifact_id=artifact_id,
            now=now,
        )
        if isinstance(pages_result, Failure):
            return pages_result

        page_ids = pages_result.unwrap()
        artifact_response.pages = page_ids

        return Success(artifact_response)

    async def _process_pdf_pages(
        self,
        pdf_content: PDFContent,
        artifact_id: str,
        now: datetime,
    ) -> Result[list[str], AppError]:
        """Process PDF pages: create pages and update text mentions.

        Args:
            pdf_content: Parsed PDF content with pages
            artifact_id: ID of the artifact
            now: Current datetime for text mention extraction

        Returns:
            Result containing list of page IDs or error

        """
        page_ids = []
        if not pdf_content.pages:
            return Success(page_ids)

        for index, pdf_page in enumerate(pdf_content.pages):
            page_name = f"Page {index + 1}"
            create_page_req = CreatePageRequest(
                name=page_name,
                artifact_id=artifact_id,
                index=index,
            )

            create_page_result = await self.create_page.execute(create_page_req)
            if isinstance(create_page_result, Failure):
                return Failure(
                    AppError(
                        "invalid_operation",
                        f"Failed to create page at index {index}: {create_page_result.failure()}",
                    ),
                )

            page_response = create_page_result.unwrap()
            page_ids.append(page_response.page_id)

            page_content = getattr(pdf_page, "page_content", None) if pdf_page else None
            if page_content and page_content.strip():
                text_mention = TextMention(
                    text=page_content,
                    date_extracted=now,
                    model_name=type(self.pdf_service).__name__,
                    confidence=None,
                    additional_model_params=None,
                    pipeline_run_id=None,
                )
                update_mention_result = await self.update_text_mention.execute(
                    page_id=page_response.page_id,
                    text_mention=text_mention,
                )
                if isinstance(update_mention_result, Failure):
                    return Failure(
                        AppError(
                            "invalid_operation",
                            f"Failed to update text mention for page {page_response.page_id}: {update_mention_result.failure()}",
                        ),
                    )

        if page_ids:
            add_pages_result = await self.add_pages.execute(
                artifact_id=artifact_id,
                page_ids=page_ids,
            )
            if isinstance(add_pages_result, Failure):
                return Failure(
                    AppError(
                        "invalid_operation",
                        f"Failed to add pages to artifact: {add_pages_result.failure()}",
                    ),
                )

        return Success(page_ids)
