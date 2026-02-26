from uuid import UUID, uuid4

from application.dtos.workflow_dtos import WorkflowNames
from application.ports.repositories.page_repository import PageRepository
from application.ports.workflow_orchestrator import WorkflowOrchestrator
from domain.value_objects.workflow_status import WorkflowStatus


class TriggerSmilesEmbeddingUseCase:
    """Trigger the SMILES embedding workflow for a page.

    Sets the page workflow status to in-progress, saves, then starts
    the Temporal workflow. Mirrors TriggerCompoundExtractionUseCase exactly.
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
            message="started via TriggerSmilesEmbeddingUseCase",
        )

        page.update_workflow_status(WorkflowNames.SMILES_EMBEDDING_WORKFLOW, workflow_status)
        self.page_repository.save(page)

        await self.workflow_orchestrator.start_smiles_embedding_workflow(page_id=page_id)

        return workflow_status
