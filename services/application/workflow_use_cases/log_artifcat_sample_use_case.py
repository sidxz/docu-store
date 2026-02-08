from uuid import UUID, uuid4

from application.dtos.workflow_dtos import WorkflowNames
from application.ports.repositories.artifact_repository import ArtifactRepository
from application.ports.workflow_orchestrator import WorkflowOrchestrator
from domain.value_objects.workflow_status import WorkflowStatus


class LogArtifactSampleUseCase:
    """Use case for logging a sample artifact with workflow status updates."""

    def __init__(
        self,
        artifact_repository: ArtifactRepository,
        workflow_orchestrator: WorkflowOrchestrator,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.workflow_orchestrator = workflow_orchestrator

    async def execute(self, artifact_id: UUID) -> WorkflowStatus:
        # Fetch the artifact from the repository
        artifact = self.artifact_repository.get_by_id(artifact_id)

        if artifact is None:
            err = f"Artifact with ID {artifact_id} not found"
            raise ValueError(err)

        # create a new workflow uuid
        workflow_id: UUID = uuid4()

        workflow_status = WorkflowStatus.in_progress(
            workflow_id=workflow_id,
            message="started via LogArtifactSampleUseCase",
        )

        # Update workflow status to 'logged'
        artifact.update_workflow_status(WorkflowNames.ARTIFACT_SAMPLE_WORKFLOW, workflow_status)

        # Save the updated artifact back to the repository
        self.artifact_repository.save(artifact)

        # Optionally, trigger a workflow for further processing
        await self.workflow_orchestrator.start_artifact_processing_workflow(
            artifact_id=artifact.id,
            storage_location=artifact.storage_location,
        )

        return workflow_status
