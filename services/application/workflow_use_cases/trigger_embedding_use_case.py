from uuid import UUID, uuid4

from application.dtos.workflow_dtos import WorkflowNames
from application.ports.repositories.page_repository import PageRepository
from application.ports.workflow_orchestrator import WorkflowOrchestrator
from domain.value_objects.workflow_status import WorkflowStatus


class TriggerEmbeddingUseCase:
    """Trigger the embedding generation workflow for a page.

    Updates the page's workflow status to in-progress, then starts
    the Temporal workflow. Mirrors TriggerCompoundExtractionUseCase.
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

        workflow_status = WorkflowStatus.in_progress(
            workflow_id=uuid4(),
            message="started via TriggerEmbeddingUseCase",
        )

        page.update_workflow_status(WorkflowNames.EMBEDDING_WORKFLOW, workflow_status)
        self.page_repository.save(page)

        await self.workflow_orchestrator.start_embedding_workflow(page_id=page_id)

        return workflow_status
