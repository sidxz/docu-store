from uuid import UUID

from application.dtos.workflow_dtos import WorkflowStartedResponse
from application.ports.workflow_orchestrator import WorkflowOrchestrator


class LogArtifactSampleUseCase:
    """Trigger artifact processing workflow.

    Starts the Temporal workflow and returns a WorkflowStartedResponse.
    Temporal is the source of truth for workflow status.
    """

    def __init__(self, workflow_orchestrator: WorkflowOrchestrator) -> None:
        self.workflow_orchestrator = workflow_orchestrator

    async def execute(self, artifact_id: UUID, storage_location: str) -> WorkflowStartedResponse:
        workflow_id = str(artifact_id)
        await self.workflow_orchestrator.start_artifact_processing_workflow(
            artifact_id=artifact_id,
            storage_location=storage_location,
        )
        return WorkflowStartedResponse(workflow_id=workflow_id)
