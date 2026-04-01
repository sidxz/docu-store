"""Trigger batch re-embedding for all artifacts in a workspace."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from application.dtos.health_dtos import ALL_REEMBED_TARGETS, BulkWorkflowResponse, ReEmbedTarget

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.repositories.artifact_read_models import ArtifactReadModel
    from application.ports.workflow_orchestrator import WorkflowOrchestrator

log = structlog.get_logger(__name__)

# Maps target name → (orchestrator method name, workflow ID prefix)
_TARGET_DISPATCH: dict[ReEmbedTarget, tuple[str, str]] = {
    "text": ("start_batch_reembed_workflow", "batch-reembed"),
    "smiles": ("start_batch_reembed_smiles_workflow", "batch-reembed-smiles"),
    "summaries": ("start_batch_reembed_summaries_workflow", "batch-reembed-summaries"),
}


class TriggerBulkReEmbedUseCase:
    """Start batch re-embed workflows for every artifact in a workspace.

    Accepts a list of targets to control which collections are re-embedded.
    Each target starts a separate Temporal workflow per artifact so they
    run in parallel.
    """

    def __init__(
        self,
        artifact_read_model: ArtifactReadModel,
        workflow_orchestrator: WorkflowOrchestrator,
    ) -> None:
        self._artifact_read_model = artifact_read_model
        self._workflow_orchestrator = workflow_orchestrator

    async def execute(
        self,
        workspace_id: UUID,
        targets: list[ReEmbedTarget] | None = None,
    ) -> BulkWorkflowResponse:
        effective_targets = targets or list(ALL_REEMBED_TARGETS)

        artifacts = await self._artifact_read_model.list_artifacts(
            workspace_id=workspace_id,
            limit=10_000,
        )

        workflow_ids: list[str] = []
        for artifact in artifacts:
            for target in effective_targets:
                method_name, wf_prefix = _TARGET_DISPATCH[target]
                try:
                    method = getattr(self._workflow_orchestrator, method_name)
                    await method(artifact_id=artifact.artifact_id)
                    workflow_ids.append(f"{wf_prefix}-{artifact.artifact_id}")
                except Exception:
                    log.warning(
                        "trigger_bulk_reembed.artifact_failed",
                        artifact_id=str(artifact.artifact_id),
                        target=target,
                    )

        log.info(
            "trigger_bulk_reembed.completed",
            total=len(workflow_ids),
            targets=effective_targets,
            workspace_id=str(workspace_id),
        )

        return BulkWorkflowResponse(
            triggered=len(workflow_ids),
            workflow_ids=workflow_ids,
            targets=effective_targets,
        )
