from uuid import UUID

from application.dtos.workflow_dtos import WorkflowStartedResponse
from application.ports.workflow_orchestrator import WorkflowOrchestrator


class TriggerCompoundExtractionUseCase:
    """Trigger the compound extraction workflow for a page.

    Starts the Temporal workflow and returns a WorkflowStartedResponse.
    Temporal is the source of truth for workflow status.
    """

    def __init__(self, workflow_orchestrator: WorkflowOrchestrator) -> None:
        self.workflow_orchestrator = workflow_orchestrator

    async def execute(self, page_id: UUID) -> WorkflowStartedResponse:
        workflow_id = f"compound-extraction-{page_id}"
        await self.workflow_orchestrator.start_compound_extraction_workflow(page_id=page_id)
        return WorkflowStartedResponse(workflow_id=workflow_id)
