"""Trigger batch re-embedding for all artifacts in a workspace."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from application.dtos.health_dtos import BulkWorkflowResponse

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.repositories.artifact_read_models import ArtifactReadModel
    from application.ports.workflow_orchestrator import WorkflowOrchestrator

log = structlog.get_logger(__name__)


class TriggerBulkReEmbedUseCase:
    """Start batch re-embed workflows for every artifact in a workspace.

    Iterates all artifacts and starts a BatchReEmbedArtifactPagesWorkflow
    for each. Failures on individual artifacts are logged and skipped
    so that one broken artifact does not block the rest.
    """

    def __init__(
        self,
        artifact_read_model: ArtifactReadModel,
        workflow_orchestrator: WorkflowOrchestrator,
    ) -> None:
        self._artifact_read_model = artifact_read_model
        self._workflow_orchestrator = workflow_orchestrator

    async def execute(self, workspace_id: UUID) -> BulkWorkflowResponse:
        artifacts = await self._artifact_read_model.list_artifacts(
            workspace_id=workspace_id,
            limit=10_000,
        )

        workflow_ids: list[str] = []
        for artifact in artifacts:
            try:
                await self._workflow_orchestrator.start_batch_reembed_workflow(
                    artifact_id=artifact.id,
                )
                workflow_ids.append(f"batch-reembed-{artifact.id}")
            except Exception:
                log.warning(
                    "trigger_bulk_reembed.artifact_failed",
                    artifact_id=str(artifact.id),
                )

        log.info(
            "trigger_bulk_reembed.completed",
            total=len(workflow_ids),
            workspace_id=str(workspace_id),
        )

        return BulkWorkflowResponse(
            triggered=len(workflow_ids),
            workflow_ids=workflow_ids,
        )
