from datetime import UTC, datetime
from typing import BinaryIO

from returns.result import Failure, Result, Success

from application.dtos.artifact_dtos import ArtifactResponse, CreateArtifactRequest
from application.dtos.blob_dtos import UploadBlobRequest, UploadBlobResponse
from application.dtos.errors import AppError
from application.dtos.page_dtos import CreatePageRequest
from application.dtos.pdf_dtos import PDFContent
from application.ports.pdf_service import PDFService
from application.use_cases.artifact_use_cases import AddPagesUseCase, CreateArtifactUseCase
from application.use_cases.blob_use_cases import UploadBlobUseCase
from application.use_cases.page_use_cases import CreatePageUseCase, UpdateTextMentionUseCase
from domain.exceptions import InfrastructureError, ValidationError
from domain.value_objects.mime_type import MimeType
from domain.value_objects.text_mention import TextMention


class ArtifactUploadSaga:
    """Orchestrates blob upload → artifact creation flow."""

    def __init__(
        self,
        upload_blob_use_case: UploadBlobUseCase,
        create_artifact_use_case: CreateArtifactUseCase,
        create_page_use_case: CreatePageUseCase,
        add_pages_use_case: AddPagesUseCase,
        update_text_mention_use_case: UpdateTextMentionUseCase,
        pdf_service: PDFService,
    ) -> None:
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

        # Step 4: Create pages from PDF content (without modifying artifact yet)
        page_ids = []
        if pdf_content.pages:
            for index, pdf_page in enumerate(pdf_content.pages):
                # Extract page name from content or use default
                page_name = f"Page {index + 1}"

                # Create page request
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

                # Step 4b: Update text mention with page content if available
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
                                f"Failed to update text mention for page at index {index}: {update_mention_result.failure()}",
                            ),
                        )

        # Step 5: Add all pages to artifact in one operation
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
        artifact_response.pages = page_ids

        return Success(artifact_response)
