from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from application.dtos.workflow_dtos import WorkflowStartedResponse

if TYPE_CHECKING:
    from application.ports.workflow_orchestrator import WorkflowOrchestrator


class TriggerArtifactParseUseCase:
    """Trigger the durable parse workflow for an artifact.

    Starts the Temporal workflow and returns a WorkflowStartedResponse.
    Temporal is the source of truth for workflow status.
    """

    def __init__(self, workflow_orchestrator: WorkflowOrchestrator) -> None:
        self.workflow_orchestrator = workflow_orchestrator

    async def execute(self, artifact_id: UUID) -> WorkflowStartedResponse:
        workflow_id = f"artifact-parse-{artifact_id}"
        await self.workflow_orchestrator.start_artifact_parse_workflow(artifact_id=artifact_id)
        return WorkflowStartedResponse(workflow_id=workflow_id)
