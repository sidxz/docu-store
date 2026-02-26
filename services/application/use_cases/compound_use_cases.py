from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from returns.result import Failure, Result, Success

from application.dtos.cser_dtos import CserCompoundResult
from application.dtos.errors import AppError
from application.dtos.page_dtos import PageResponse
from application.dtos.workflow_dtos import WorkflowNames
from application.mappers.page_mappers import PageMapper
from application.ports.cser_service import CserService
from application.ports.external_event_publisher import ExternalEventPublisher
from application.ports.repositories.artifact_repository import ArtifactRepository
from application.ports.repositories.page_repository import PageRepository
from domain.exceptions import AggregateNotFoundError, ConcurrencyError, ValidationError

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.smiles_validator import SmilesValidator

from domain.value_objects.compound_mention import CompoundMention
from domain.value_objects.workflow_status import WorkflowStatus

logger = structlog.get_logger()

_MODEL_NAME = "structflo-cser"


class ExtractCompoundMentionsUseCase:
    """Run the CSER pipeline on a page image and persist extracted compounds.

    This use case:
    1. Loads the Page aggregate (to get artifact_id and page index)
    2. Loads the Artifact aggregate (to get the PDF storage key)
    3. Calls CserService to render the page and extract compound pairs
    4. Maps raw results to CompoundMention value objects (skipping any without SMILES)
    5. Updates the Page aggregate and persists it
    """

    def __init__(
        self,
        page_repository: PageRepository,
        artifact_repository: ArtifactRepository,
        cser_service: CserService,
        smiles_validator: SmilesValidator,
        external_event_publisher: ExternalEventPublisher | None = None,
    ) -> None:
        self.page_repository = page_repository
        self.artifact_repository = artifact_repository
        self.cser_service = cser_service
        self.smiles_validator = smiles_validator
        self.external_event_publisher = external_event_publisher

    def _map_to_compound_mention(self, result: CserCompoundResult) -> CompoundMention | None:
        """Map a raw CserCompoundResult to a CompoundMention value object.

        Returns None if the result has no SMILES (cannot construct a valid CompoundMention).
        Validates and canonicalizes the SMILES using the configured validator.
        """
        if not result.smiles or not result.smiles.strip():
            return None
        is_valid = self.smiles_validator.validate(result.smiles)
        canonical = self.smiles_validator.canonicalize(result.smiles) if is_valid else None
        return CompoundMention(
            smiles=result.smiles,
            canonical_smiles=canonical,
            is_smiles_valid=is_valid,
            extracted_id=result.label_text,
            confidence=result.match_confidence,
            date_extracted=datetime.now(UTC),
            model_name=_MODEL_NAME,
        )

    async def execute(self, page_id: UUID) -> Result[PageResponse, AppError]:
        try:
            logger.info("extract_compound_mentions_start", page_id=str(page_id))

            page = self.page_repository.get_by_id(page_id)
            artifact = self.artifact_repository.get_by_id(page.artifact_id)

            logger.info(
                "extract_compound_mentions_running_cser",
                page_id=str(page_id),
                artifact_id=str(artifact.id),
                page_index=page.index,
            )

            raw_results: list[CserCompoundResult] = (
                self.cser_service.extract_compounds_from_pdf_page(
                    storage_key=artifact.storage_location,
                    page_index=page.index,
                )
            )

            compound_mentions = [
                mention
                for result in raw_results
                if (mention := self._map_to_compound_mention(result)) is not None
            ]

            logger.info(
                "extract_compound_mentions_mapped",
                page_id=str(page_id),
                total_raw=len(raw_results),
                valid=len(compound_mentions),
            )

            page.update_compound_mentions(compound_mentions)

            existing = page.workflow_statuses.get(WorkflowNames.COMPOUND_EXTRACTION_WORKFLOW)
            page.update_workflow_status(
                WorkflowNames.COMPOUND_EXTRACTION_WORKFLOW,
                WorkflowStatus.completed(
                    message=f"extracted {len(compound_mentions)} compounds",
                    workflow_id=existing.workflow_id if existing else None,
                    started_at=existing.started_at if existing else None,
                ),
            )

            self.page_repository.save(page)

            result = PageMapper.to_page_response(page)

            if self.external_event_publisher:
                await self.external_event_publisher.notify_page_updated(result)

            logger.info("extract_compound_mentions_success", page_id=str(page_id))
            return Success(result)

        except AggregateNotFoundError as e:
            logger.warning(
                "extract_compound_mentions_not_found", page_id=str(page_id), error=str(e)
            )
            return Failure(AppError("not_found", str(e)))
        except ValidationError as e:
            logger.warning(
                "extract_compound_mentions_validation_error", page_id=str(page_id), error=str(e)
            )
            return Failure(AppError("validation", str(e)))
        except ConcurrencyError as e:
            logger.warning(
                "extract_compound_mentions_concurrency_error", page_id=str(page_id), error=str(e)
            )
            return Failure(AppError("concurrency", str(e)))
        except Exception as e:
            logger.exception(
                "extract_compound_mentions_unexpected_error",
                page_id=str(page_id),
                error=str(e),
            )
            return Failure(AppError("internal_error", f"Unexpected error: {e!s}"))
