"""Trigger use case: start document metadata extraction for page 0 of an artifact."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from application.dtos.workflow_dtos import WorkflowStartedResponse

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.repositories.page_repository import PageRepository
    from application.ports.workflow_orchestrator import WorkflowOrchestrator

logger = structlog.get_logger()


class TriggerDocMetadataExtractionUseCase:
    def __init__(
        self,
        page_repository: PageRepository,
        workflow_orchestrator: WorkflowOrchestrator,
    ) -> None:
        self.page_repository = page_repository
        self.workflow_orchestrator = workflow_orchestrator

    async def execute(self, page_id: UUID) -> WorkflowStartedResponse | None:
        page = self.page_repository.get_by_id(page_id)

        # Only extract metadata from the first page (cover/title page)
        if page.index != 0:
            logger.debug(
                "trigger_doc_metadata.skip_non_first_page",
                page_id=str(page_id),
                page_index=page.index,
            )
            return None

        artifact_id = page.artifact_id
        workflow_id = f"doc-metadata-{artifact_id}"

        await self.workflow_orchestrator.start_doc_metadata_extraction_workflow(
            artifact_id=artifact_id,
            page_id=page_id,
        )

        logger.info(
            "trigger_doc_metadata.workflow_started",
            page_id=str(page_id),
            artifact_id=str(artifact_id),
        )
        return WorkflowStartedResponse(workflow_id=workflow_id)
