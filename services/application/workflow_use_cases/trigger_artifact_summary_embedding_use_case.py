"""Trigger use case: start the artifact summary embedding Temporal workflow."""

from uuid import UUID

import structlog

from application.dtos.workflow_dtos import WorkflowStartedResponse
from application.ports.workflow_orchestrator import WorkflowOrchestrator

logger = structlog.get_logger()


class TriggerArtifactSummaryEmbeddingUseCase:
    """Start the artifact summary embedding workflow.

    Called from the pipeline worker when ``Artifact.SummaryCandidateUpdated``
    is received.
    """

    def __init__(self, workflow_orchestrator: WorkflowOrchestrator) -> None:
        self.workflow_orchestrator = workflow_orchestrator

    async def execute(self, artifact_id: UUID) -> WorkflowStartedResponse:
        logger.info("trigger_artifact_summary_embedding", artifact_id=str(artifact_id))
        await self.workflow_orchestrator.start_artifact_summary_embedding_workflow(
            artifact_id=artifact_id,
        )
        return WorkflowStartedResponse(workflow_id=f"artifact-summary-embedding-{artifact_id}")
