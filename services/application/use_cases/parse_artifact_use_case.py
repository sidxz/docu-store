from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, UUID, uuid5

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from application.dtos.page_dtos import CreatePageRequest
from application.use_cases.storage_keys import render_pdf_key
from domain.value_objects.mime_type import MimeType
from domain.value_objects.text_mention import TextMention
from infrastructure.file_services.segmentation import segment_document

if TYPE_CHECKING:
    from application.ports.blob_store import BlobStore
    from application.ports.document_parser import DocumentParser
    from application.ports.office_converter import OfficeToPdfConverter
    from application.ports.repositories.artifact_repository import ArtifactRepository
    from application.ports.repositories.page_repository import PageRepository
    from application.use_cases.artifact_use_cases import AddPagesUseCase
    from application.use_cases.page_use_cases import CreatePageUseCase, UpdateTextMentionUseCase

log = structlog.get_logger(__name__)


def page_id_for(artifact_id: UUID, index: int) -> UUID:
    return uuid5(NAMESPACE_URL, f"docu-store/artifact/{artifact_id}/page/{index}")


class ParseArtifactUseCase:
    """Parse an artifact into a structured document and create its Pages (idempotent)."""

    def __init__(
        self,
        parsers: dict[MimeType, DocumentParser],
        blob_store: BlobStore,
        artifact_repository: ArtifactRepository,
        page_repository: PageRepository,
        create_page_use_case: CreatePageUseCase,
        update_text_mention_use_case: UpdateTextMentionUseCase,
        add_pages_use_case: AddPagesUseCase,
        office_converter: OfficeToPdfConverter,
    ) -> None:
        self.parsers = parsers
        self.blob_store = blob_store
        self.artifact_repository = artifact_repository
        self.page_repository = page_repository
        self.create_page = create_page_use_case
        self.update_text_mention = update_text_mention_use_case
        self.add_pages = add_pages_use_case
        self.office_converter = office_converter

    async def execute(self, artifact_id: UUID) -> Result[list[UUID], AppError]:
        artifact = self.artifact_repository.get_by_id(artifact_id)  # sync, no await
        parser = self.parsers.get(artifact.mime_type)
        if parser is None:
            return Failure(AppError("validation", f"No parser for MIME type: {artifact.mime_type}"))

        # Office formats (PPTX, …) are rendered to a derived PDF first, then the one
        # PDF pipeline takes over. render_key == storage_location for native PDFs.
        render_key = render_pdf_key(artifact)
        if artifact.mime_type != MimeType.PDF:
            self.office_converter.convert_to_pdf(artifact.storage_location, render_key)

        parsed = parser.parse(render_key)

        # Persist page images (same keys chat already uses).
        for page in parsed.pages:
            self.blob_store.put_stream(
                f"artifacts/{artifact_id}/pages/{page.index}.png",
                io.BytesIO(page.png),
                mime_type="image/png",
            )
            if page.thumb:
                self.blob_store.put_stream(
                    f"artifacts/{artifact_id}/pages/{page.index}_thumb.jpg",
                    io.BytesIO(page.thumb),
                    mime_type="image/jpeg",
                )

        # Persist the structure-only IR blob.
        self.blob_store.put_stream(
            f"artifacts/{artifact_id}/parsed/document.json",
            io.BytesIO(parsed.document.model_dump_json().encode()),
            mime_type="application/json",
        )

        segments = segment_document(parsed.document, parsed.pages, str(artifact.mime_type))
        now = datetime.now(tz=UTC)
        page_ids: list[UUID] = []

        for seg in segments:
            pid = page_id_for(artifact_id, seg.index)
            page_ids.append(pid)
            create_res = await self.create_page.execute(
                CreatePageRequest(
                    name=f"Page {seg.index + 1}",
                    artifact_id=artifact_id,
                    index=seg.index,
                    page_id=pid,
                ),
                # No request auth in the parse activity — carry workspace/owner from the
                # artifact (explicit args, not request data) so pages are workspace-scoped.
                workspace_id=artifact.workspace_id,
                owner_id=artifact.owner_id,
            )

            if not seg.text.strip():
                continue

            # ponytail: idempotent text-set — fresh page always needs text; on retry (create_res is
            # Failure meaning page already exists) load and skip if text unchanged, avoiding re-emit
            # of TextMentionUpdated which would chain expensive LLM summarization/NER downstream.
            if isinstance(create_res, Failure):
                existing = self.page_repository.get_by_id(pid)
                if existing.text_mention is not None and existing.text_mention.text == seg.text:
                    log.debug("parse.text_unchanged_skipping", page_id=str(pid))
                    continue

            text_res = await self.update_text_mention.execute(
                page_id=pid,
                text_mention=TextMention(
                    text=seg.text,
                    date_extracted=now,
                    model_name="DoclingParser",
                    confidence=None,
                    additional_model_params=None,
                    pipeline_run_id=None,
                ),
            )
            if isinstance(text_res, Failure):
                return text_res

        if page_ids:
            add_res = await self.add_pages.execute(artifact_id=artifact_id, page_ids=page_ids)
            if isinstance(add_res, Failure):
                return add_res

        return Success(page_ids)
