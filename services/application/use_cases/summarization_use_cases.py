from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from application.mappers.page_mappers import PageMapper
from domain.exceptions import AggregateNotFoundError, ConcurrencyError, ValidationError
from domain.value_objects.summary_candidate import SummaryCandidate

if TYPE_CHECKING:
    from uuid import UUID

    from application.dtos.page_dtos import PageResponse
    from application.ports.blob_store import BlobStore
    from application.ports.external_event_publisher import ExternalEventPublisher
    from application.ports.llm_client import LLMClientPort
    from application.ports.prompt_repository import PromptRepositoryPort
    from application.ports.repositories.artifact_repository import ArtifactRepository
    from application.ports.repositories.page_repository import PageRepository

log = structlog.get_logger(__name__)

# Threshold (chars) below which text is considered too sparse to use as the primary source.
_TEXT_THRESHOLD = 100


class SummarizePageUseCase:
    """Generate an LLM summary for a single page and persist it as SummaryCandidate.

    Summarization mode is selected automatically:
      - HYBRID      text >= 100 chars  →  text prompt + page image
      - IMAGE_ONLY  text < 100 chars, image in blob store  →  image only
      - TEXT_ONLY   no image available  →  text prompt only

    Skips pages whose summary_candidate.is_locked is True (human correction present).
    """

    def __init__(
        self,
        page_repository: PageRepository,
        artifact_repository: ArtifactRepository,
        llm_client: LLMClientPort,
        prompt_repository: PromptRepositoryPort,
        blob_store: BlobStore,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.page_repository = page_repository
        self.artifact_repository = artifact_repository
        self.llm_client = llm_client
        self.prompt_repository = prompt_repository
        self.blob_store = blob_store
        self.external_event_publisher = external_event_publisher

    async def execute(self, page_id: UUID) -> Result[PageResponse, AppError]:
        try:
            log.info("summarize_page.start", page_id=str(page_id))

            page = self.page_repository.get_by_id(page_id)
            artifact = self.artifact_repository.get_by_id(page.artifact_id)

            # Respect human corrections — do not overwrite locked summaries.
            if page.summary_candidate and page.summary_candidate.is_locked:
                log.info("summarize_page.skipped_locked", page_id=str(page_id))
                return Success(PageMapper.to_page_response(page))

            slide_text = (
                page.text_mention.text.strip() if page.text_mention and page.text_mention.text else ""
            )
            artifact_title = artifact.source_filename or "Unknown"
            page_index = page.index + 1  # 1-based for the prompt

            image_key = f"artifacts/{artifact.id}/pages/{page.index}.png"
            image_exists = self.blob_store.exists(image_key)

            # Determine mode and call the appropriate LLM path
            if len(slide_text) >= _TEXT_THRESHOLD:
                mode = "hybrid"
                rendered = await self.prompt_repository.render_prompt(
                    "page_summarization_hybrid",
                    slide_text=slide_text,
                    artifact_title=artifact_title,
                    page_index=str(page_index),
                )
                image_b64 = _load_image_b64(self.blob_store, image_key) if image_exists else None
                if image_b64:
                    summary_text = await self.llm_client.complete_with_image(rendered, image_b64)
                else:
                    summary_text = await self.llm_client.complete(rendered)

            elif image_exists:
                mode = "image_only"
                rendered = await self.prompt_repository.render_prompt(
                    "page_summarization_image_only",
                    artifact_title=artifact_title,
                    page_index=str(page_index),
                )
                image_b64 = _load_image_b64(self.blob_store, image_key)
                summary_text = await self.llm_client.complete_with_image(rendered, image_b64)

            else:
                mode = "text_only"
                rendered = await self.prompt_repository.render_prompt(
                    "page_summarization_text_only",
                    slide_text=slide_text,
                    artifact_title=artifact_title,
                    page_index=str(page_index),
                )
                summary_text = await self.llm_client.complete(rendered)

            model_info = await self.llm_client.get_model_info()
            model_name = f"{model_info.get('provider', 'unknown')}/{model_info.get('model_name', 'unknown')}"

            log.info(
                "summarize_page.llm_done",
                page_id=str(page_id),
                mode=mode,
                model=model_name,
                summary_len=len(summary_text),
            )

            candidate = SummaryCandidate(
                summary=summary_text.strip(),
                model_name=model_name,
                date_extracted=datetime.now(UTC),
                confidence=None,
                additional_model_params={"mode": mode},
                pipeline_run_id=None,
                is_locked=False,
                hil_correction=None,
            )
            page.update_summary_candidate(candidate)

            self.page_repository.save(page)
            result = PageMapper.to_page_response(page)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_page_updated(result)

            log.info("summarize_page.success", page_id=str(page_id), mode=mode)
            return Success(result)

        except AggregateNotFoundError as e:
            log.warning("summarize_page.not_found", page_id=str(page_id), error=str(e))
            return Failure(AppError("not_found", str(e)))
        except ValidationError as e:
            log.warning("summarize_page.validation_error", page_id=str(page_id), error=str(e))
            return Failure(AppError("validation", str(e)))
        except ConcurrencyError as e:
            log.warning("summarize_page.concurrency_error", page_id=str(page_id), error=str(e))
            return Failure(AppError("concurrency", str(e)))
        except Exception as e:
            log.exception("summarize_page.unexpected_error", page_id=str(page_id), error=str(e))
            return Failure(AppError("internal_error", f"Unexpected error: {e!s}"))


def _load_image_b64(blob_store: BlobStore, key: str) -> str:
    """Read a blob and return it as a base64-encoded string."""
    raw = blob_store.get_bytes(key)
    return base64.b64encode(raw).decode("ascii")
