"""Trigger use case: start the page summary embedding Temporal workflow."""

from uuid import UUID

import structlog

from application.dtos.workflow_dtos import WorkflowStartedResponse
from application.ports.workflow_orchestrator import WorkflowOrchestrator

logger = structlog.get_logger()


class TriggerPageSummaryEmbeddingUseCase:
    """Start the page summary embedding workflow for a page.

    Called from the pipeline worker when ``Page.SummaryCandidateUpdated``
    is received.  No precondition check — if the summary exists the
    Temporal activity will find it; if it doesn't, the activity returns
    a validation failure (non-fatal).
    """

    def __init__(self, workflow_orchestrator: WorkflowOrchestrator) -> None:
        self.workflow_orchestrator = workflow_orchestrator

    async def execute(self, page_id: UUID) -> WorkflowStartedResponse:
        logger.info("trigger_page_summary_embedding", page_id=str(page_id))
        await self.workflow_orchestrator.start_page_summary_embedding_workflow(page_id=page_id)
        return WorkflowStartedResponse(workflow_id=f"page-summary-embedding-{page_id}")
