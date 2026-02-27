from __future__ import annotations

from uuid import UUID, uuid4

import structlog

from application.dtos.workflow_dtos import WorkflowNames
from application.ports.repositories.page_repository import PageRepository
from application.ports.workflow_orchestrator import WorkflowOrchestrator
from domain.value_objects.workflow_status import WorkflowStatus

log = structlog.get_logger(__name__)


class TriggerPageSummarizationUseCase:
    """Set a page's summarization workflow status to in-progress and start Temporal.

    Called by both the pipeline worker (on TextMentionUpdated events) and the
    manual API endpoint. Both paths are identical — Temporal workflow ID
    `page-summarization-{page_id}` provides idempotency.
    """

    def __init__(
        self,
        page_repository: PageRepository,
        workflow_orchestrator: WorkflowOrchestrator,
    ) -> None:
        self.page_repository = page_repository
        self.workflow_orchestrator = workflow_orchestrator

    async def execute(self, page_id: UUID) -> WorkflowStatus:
        page = self.page_repository.get_by_id(page_id)

        if page is None:
            msg = f"Page {page_id} not found"
            raise ValueError(msg)

        workflow_id = uuid4()
        workflow_status = WorkflowStatus.in_progress(
            workflow_id=workflow_id,
            message="started via TriggerPageSummarizationUseCase",
        )

        page.update_workflow_status(WorkflowNames.PAGE_SUMMARIZATION_WORKFLOW, workflow_status)
        self.page_repository.save(page)

        await self.workflow_orchestrator.start_page_summarization_workflow(page_id=page_id)

        log.info("trigger_page_summarization.started", page_id=str(page_id), workflow_id=str(workflow_id))
        return workflow_status
