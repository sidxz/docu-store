from uuid import UUID, uuid4

from application.dtos.workflow_dtos import WorkflowNames
from application.ports.repositories.page_repository import PageRepository
from application.ports.workflow_orchestrator import WorkflowOrchestrator
from domain.value_objects.workflow_status import WorkflowStatus


class TriggerCompoundExtractionUseCase:
    """Trigger the compound extraction workflow for a page.

    Updates the page's workflow status to in-progress, then starts
    the Temporal workflow. Mirrors the pattern of LogArtifactSampleUseCase.
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
            msg = f"Page with ID {page_id} not found"
            raise ValueError(msg)

        workflow_id = uuid4()
        workflow_status = WorkflowStatus.in_progress(
            workflow_id=workflow_id,
            message="started via TriggerCompoundExtractionUseCase",
        )

        page.update_workflow_status(WorkflowNames.COMPOUND_EXTRACTION_WORKFLOW, workflow_status)
        self.page_repository.save(page)

        await self.workflow_orchestrator.start_compound_extraction_workflow(page_id=page_id)

        return workflow_status
