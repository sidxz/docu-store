"""Use case: extract document-level metadata (title, authors, date) from page text."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from domain.value_objects.author_mention import AuthorMention
from domain.value_objects.presentation_date import PresentationDate
from domain.value_objects.title_mention import TitleMention

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.blob_store import BlobStore
    from application.ports.external_event_publisher import ExternalEventPublisher
    from application.ports.llm_client import LLMClientPort
    from application.ports.prompt_repository import PromptRepositoryPort
    from application.ports.repositories.artifact_repository import ArtifactRepository
    from application.ports.repositories.page_repository import PageRepository
    from application.ports.structured_extractor import ExtractedField, StructuredExtractorPort
    from application.ports.title_extractor import TitleExtractorPort
    from domain.aggregates.page import Page

logger = structlog.get_logger()

# GLiNER2 schema — authors and dates only (title handled by font analysis)
_EXTRACTION_SCHEMA = [
    "author_name::str::Name of an author or presenter",
    "presentation_date::str::Date of presentation, publication, or creation",
]

_CONFIDENCE_THRESHOLD = 0.4  # Minimum to accept without LLM fallback
_LLM_DEFAULT_CONFIDENCE = 0.7  # Confidence assigned to LLM-extracted fields
_MAX_CASCADE_PAGES = 3  # Max pages to try before giving up


@dataclass
class _RawMetadata:
    """Intermediate extraction results before building domain VOs."""

    title: str | None = None
    title_confidence: float = 0.0
    title_from_llm: bool = False
    authors: list[dict[str, str | None]] = field(default_factory=list)
    author_confidence: float = 1.0
    authors_from_llm: bool = False
    date_str: str | None = None
    date_confidence: float = 0.0
    date_from_llm: bool = False
    date_source: str = "gliner2"

    @property
    def has_title(self) -> bool:
        return self.title is not None and self.title_confidence >= _CONFIDENCE_THRESHOLD

    @property
    def has_authors(self) -> bool:
        return len(self.authors) > 0

    @property
    def has_date(self) -> bool:
        return self.date_str is not None and self.date_confidence >= _CONFIDENCE_THRESHOLD

    @property
    def is_complete(self) -> bool:
        return self.has_title and self.has_authors and self.has_date


class ExtractDocumentMetadataUseCase:
    """Extract title, authors, and date from page text.

    Title: font-size heuristic (PyMuPDF) → LLM fallback
    Authors + Date: GLiNER2 structured extraction → LLM fallback
    """

    def __init__(  # noqa: PLR0913
        self,
        page_repository: PageRepository,
        artifact_repository: ArtifactRepository,
        structured_extractor: StructuredExtractorPort,
        llm_client: LLMClientPort,
        prompt_repository: PromptRepositoryPort,
        title_extractor: TitleExtractorPort,
        blob_store: BlobStore,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.page_repository = page_repository
        self.artifact_repository = artifact_repository
        self.structured_extractor = structured_extractor
        self.llm_client = llm_client
        self.prompt_repository = prompt_repository
        self.title_extractor = title_extractor
        self.blob_store = blob_store
        self.external_event_publisher = external_event_publisher

    async def execute(self, artifact_id: UUID, page_id: UUID) -> Result[dict, AppError]:  # noqa: C901, PLR0912, PLR0915
        try:
            artifact = self.artifact_repository.get_by_id(artifact_id)
            now = datetime.now(UTC)

            page_ids_to_try = self._build_page_cascade(artifact.pages, page_id)

            logger.info(
                "extract_doc_metadata.start",
                artifact_id=str(artifact_id),
                page_id=str(page_id),
                cascade_pages=len(page_ids_to_try),
            )

            raw = _RawMetadata()
            pages_tried = 0
            first_page_text: str | None = None

            # Load PDF once for font-based title extraction across all pages
            with self.blob_store.get_file(artifact.storage_location) as pdf_path:
                for pid in page_ids_to_try:
                    page = self._load_page(pid)
                    if page is None:
                        continue

                    page_text = page.text_mention.text if page.text_mention else None
                    has_text = bool(page_text and page_text.strip())

                    if first_page_text is None and has_text:
                        first_page_text = page_text

                    pages_tried += 1

                    # Font-based title extraction (fast, ~1ms)
                    if not raw.has_title:
                        candidate = self.title_extractor.extract_title(pdf_path, page.index)
                        if candidate:
                            raw.title = candidate.title
                            raw.title_confidence = candidate.confidence

                    # GLiNER2 for authors + date (needs page text)
                    if has_text and (not raw.has_authors or not raw.has_date):
                        gliner_fields = await self.structured_extractor.extract(
                            page_text,
                            _EXTRACTION_SCHEMA,
                            threshold=0.3,
                        )
                        page_raw = self._parse_gliner_fields(gliner_fields)
                        self._merge_raw(raw, page_raw)

                    # Regex date scan — catches compact YYYYMMDD and other formats
                    # that NER models miss (fast, ~0ms)
                    if has_text and not raw.has_date:
                        self._try_regex_date(raw, page_text)

                    logger.debug(
                        "extract_doc_metadata.page_extracted",
                        page_id=str(pid),
                        page_index=page.index,
                        has_title=raw.has_title,
                        has_authors=raw.has_authors,
                        has_date=raw.has_date,
                    )

                    if raw.is_complete:
                        break

            if pages_tried == 0:
                logger.info("extract_doc_metadata.skip_no_pages", artifact_id=str(artifact_id))
                return Success({"status": "skipped", "reason": "no usable pages"})

            # LLM fallback for any still-missing fields
            if not raw.is_complete and first_page_text:
                await self._apply_llm_fallback(raw, first_page_text)

            # Filename date fallback — many files contain dates in their name
            if not raw.has_date and artifact.source_filename:
                self._try_filename_date(raw, artifact.source_filename)

            # Build domain VOs and update aggregate
            title_mention = self._build_title(raw, now)
            author_mentions = self._build_authors(raw, now)
            presentation_date = self._build_date(raw, now)

            if title_mention:
                artifact.update_title_mention(title_mention)
            if author_mentions:
                artifact.update_author_mentions(author_mentions)
            if presentation_date is not None:
                artifact.update_presentation_date(presentation_date)
            if title_mention or author_mentions or presentation_date is not None:
                self.artifact_repository.save(artifact)

                if self.external_event_publisher:
                    from application.mappers.artifact_mappers import ArtifactMapper  # noqa: PLC0415

                    artifact_response = ArtifactMapper.to_artifact_response(artifact)
                    await self.external_event_publisher.notify_artifact_updated(
                        artifact_response,
                        sub_type="DocumentMetadataUpdated",
                    )

            logger.info(
                "extract_doc_metadata.success",
                artifact_id=str(artifact_id),
                pages_tried=pages_tried,
                has_title=title_mention is not None,
                title_method="font" if title_mention and not raw.title_from_llm else "llm",
                author_count=len(author_mentions),
                has_date=presentation_date is not None,
            )
            return Success(
                {
                    "status": "success",
                    "artifact_id": str(artifact_id),
                    "title": raw.title,
                    "author_count": len(author_mentions),
                    "has_date": presentation_date is not None,
                    "pages_tried": pages_tried,
                },
            )

        except Exception as e:
            from domain.exceptions import AggregateNotFoundError, ConcurrencyError  # noqa: PLC0415

            if isinstance(e, AggregateNotFoundError):
                return Failure(AppError("not_found", str(e)))
            if isinstance(e, ConcurrencyError):
                return Failure(AppError("concurrency", str(e)))
            logger.exception("extract_doc_metadata.error", artifact_id=str(artifact_id))
            return Failure(AppError("internal_error", f"Unexpected error: {e!s}"))

    # ── Private helpers ───────────────────────────────────────────────────

    @staticmethod
    def _build_page_cascade(artifact_pages: tuple[UUID, ...], first_page_id: UUID) -> list[UUID]:
        """Build ordered list of page IDs to try: requested page first, then subsequent."""
        result = [first_page_id]
        for pid in artifact_pages:
            if pid != first_page_id:
                result.append(pid)
            if len(result) >= _MAX_CASCADE_PAGES:
                break
        return result

    def _load_page(self, page_id: UUID) -> Page | None:
        """Load a page, returning None if not found."""
        try:
            return self.page_repository.get_by_id(page_id)
        except Exception:  # noqa: BLE001
            logger.warning("extract_doc_metadata.page_load_failed", page_id=str(page_id))
            return None

    @staticmethod
    def _parse_gliner_fields(fields: list[ExtractedField]) -> _RawMetadata:
        """Group GLiNER2 fields into a structured intermediate result."""
        raw = _RawMetadata()

        author_fields = [f for f in fields if f.name == "author_name"]
        for af in author_fields:
            raw.authors.append({"name": af.value})
            raw.author_confidence = min(raw.author_confidence, af.score)

        date_fields = [f for f in fields if f.name == "presentation_date"]
        if date_fields:
            best = max(date_fields, key=lambda f: f.score)
            raw.date_str = best.value
            raw.date_confidence = best.score

        return raw

    @staticmethod
    def _merge_raw(target: _RawMetadata, source: _RawMetadata) -> None:
        """Merge source into target — higher confidence wins per field."""
        if source.title and source.title_confidence > target.title_confidence:
            target.title = source.title
            target.title_confidence = source.title_confidence
            target.title_from_llm = source.title_from_llm

        if source.authors and (
            not target.authors or source.author_confidence > target.author_confidence
        ):
            target.authors = source.authors
            target.author_confidence = source.author_confidence
            target.authors_from_llm = source.authors_from_llm

        if source.date_str and source.date_confidence > target.date_confidence:
            target.date_str = source.date_str
            target.date_confidence = source.date_confidence
            target.date_from_llm = source.date_from_llm
            target.date_source = source.date_source

    async def _apply_llm_fallback(self, raw: _RawMetadata, text: str) -> None:
        logger.info(
            "extract_doc_metadata.llm_fallback",
            title_conf=raw.title_confidence,
            author_count=len(raw.authors),
            date_conf=raw.date_confidence,
        )
        llm_result = await self._llm_extract(text)
        if not llm_result:
            return

        if not raw.has_title and llm_result.get("title"):
            raw.title = llm_result["title"]
            raw.title_confidence = _LLM_DEFAULT_CONFIDENCE
            raw.title_from_llm = True

        if not raw.has_authors and llm_result.get("authors"):
            raw.authors = [
                {"name": a.get("name", a) if isinstance(a, dict) else a}
                for a in llm_result["authors"]
            ]
            raw.authors_from_llm = True

        if not raw.has_date and llm_result.get("date"):
            raw.date_str = llm_result["date"]
            raw.date_confidence = _LLM_DEFAULT_CONFIDENCE
            raw.date_from_llm = True
            raw.date_source = "llm"

    @classmethod
    def _try_regex_date(cls, raw: _RawMetadata, text: str) -> None:
        """Scan page text for date patterns that NER models miss (e.g. YYYYMMDD)."""
        parsed = cls._parse_date(text)
        if parsed:
            raw.date_str = text
            raw.date_confidence = 0.8
            raw.date_from_llm = False
            raw.date_source = "regex"
            logger.info("extract_doc_metadata.date_from_regex")

    @classmethod
    def _try_filename_date(cls, raw: _RawMetadata, filename: str) -> None:
        """Try to extract a date from the filename as a last resort."""
        from pathlib import PurePath  # noqa: PLC0415

        stem = PurePath(filename).stem
        parsed = cls._parse_date(stem)
        if parsed:
            raw.date_str = stem
            raw.date_confidence = 0.5
            raw.date_from_llm = False
            raw.date_source = "filename"
            logger.info("extract_doc_metadata.date_from_filename", filename=filename)

    @staticmethod
    def _build_title(raw: _RawMetadata, now: datetime) -> TitleMention | None:
        if not raw.title or not raw.title.strip():
            return None
        return TitleMention(
            title=raw.title.strip(),
            confidence=raw.title_confidence,
            date_extracted=now,
            model_name="llm-fallback" if raw.title_from_llm else "font-analysis",
        )

    @staticmethod
    def _build_authors(raw: _RawMetadata, now: datetime) -> list[AuthorMention]:
        model = "llm-fallback" if raw.authors_from_llm else "gliner2"
        mentions: list[AuthorMention] = []
        for author_data in raw.authors:
            name = author_data.get("name", "")
            if name and name.strip():
                mentions.append(
                    AuthorMention(
                        name=name.strip(),
                        confidence=raw.author_confidence,
                        date_extracted=now,
                        model_name=model,
                    ),
                )
        return mentions

    @staticmethod
    def _build_date(raw: _RawMetadata, now: datetime) -> PresentationDate | None:
        if not raw.date_str:
            return None
        parsed = ExtractDocumentMetadataUseCase._parse_date(raw.date_str)
        if not parsed:
            return None
        model_map = {
            "gliner2": "gliner2",
            "regex": "regex",
            "llm": "llm-fallback",
            "filename": "filename",
        }
        return PresentationDate(
            date=parsed,
            source=raw.date_source,
            confidence=raw.date_confidence,
            date_extracted=now,
            model_name=model_map.get(raw.date_source, raw.date_source),
        )

    async def _llm_extract(self, text: str) -> dict | None:
        """Use LLM to extract metadata when primary methods fail."""
        try:
            prompt = await self.prompt_repository.render_prompt(
                "document_metadata_extraction",
                page_text=text[:3000],
            )
            response = await self.llm_client.complete(prompt)
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                cleaned = cleaned.removesuffix("```").strip()
            return json.loads(cleaned)
        except Exception:
            logger.exception("extract_doc_metadata.llm_fallback_failed")
            return None

    @staticmethod
    def _parse_date(date_str: str) -> datetime | None:
        """Parse a date string, handling compact YYYYMMDD and natural language formats."""
        import re  # noqa: PLC0415

        try:
            import dateparser  # noqa: PLC0415

            # Try YYYY-MM-DD / YYYY_MM_DD / YYYY.MM.DD first (explicit separators = high intent)
            match = re.search(r"(\d{4})[-_.](\d{1,2})[-_.](\d{1,2})", date_str)
            if match:
                normalized = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                parsed = dateparser.parse(
                    normalized,
                    settings={"PREFER_DAY_OF_MONTH": "first", "RETURN_AS_TIMEZONE_AWARE": False},
                )
                if parsed:
                    return parsed.replace(tzinfo=UTC)

            # Try compact YYYYMMDD (common in scientific filenames and slide metadata)
            match = re.search(r"(?<!\d)(\d{4})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)", date_str)
            if match:
                normalized = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                parsed = dateparser.parse(
                    normalized,
                    settings={"PREFER_DAY_OF_MONTH": "first", "RETURN_AS_TIMEZONE_AWARE": False},
                )
                if parsed:
                    return parsed.replace(tzinfo=UTC)

            # Fall back to dateparser on the raw string (handles "March 2024", etc.)
            parsed = dateparser.parse(
                date_str,
                settings={"PREFER_DAY_OF_MONTH": "first", "RETURN_AS_TIMEZONE_AWARE": False},
            )
            if parsed:
                return parsed.replace(tzinfo=UTC)
        except Exception:
            logger.exception("extract_doc_metadata.date_parse_failed", date_str=date_str)
        return None
