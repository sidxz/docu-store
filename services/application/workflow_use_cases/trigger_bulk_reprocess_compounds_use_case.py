"""Trigger CSER compound re-extraction for every artifact in a workspace.

Purges stale/orphan compound vectors first, then starts the per-page compound
extraction workflow for every page. The existing event cascade
(``Page.CompoundMentionsUpdated`` → SMILES embedding) re-embeds the freshly
extracted compounds idempotently, so no explicit re-embed pass is needed.

See ``design_docs/BULK_REPROCESS_COMPOUNDS.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from application.dtos.health_dtos import BulkWorkflowResponse

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.compound_vector_store import CompoundVectorStore
    from application.ports.repositories.artifact_read_models import ArtifactReadModel
    from application.ports.repositories.page_read_models import PageReadModel
    from application.ports.workflow_orchestrator import WorkflowOrchestrator

log = structlog.get_logger(__name__)


class TriggerBulkReprocessCompoundsUseCase:
    """Re-run CSER extraction across all artifacts in a workspace.

    1. Purge the workspace's compound vectors (removes orphans the per-page
       delete-then-upsert cannot reach).
    2. Start ``ExtractCompoundMentionsWorkflow`` for every page. Extraction
       replaces the page's compound mentions and emits
       ``Page.CompoundMentionsUpdated``, which cascades to SMILES embedding.
    """

    def __init__(
        self,
        artifact_read_model: ArtifactReadModel,
        page_read_model: PageReadModel,
        compound_vector_store: CompoundVectorStore,
        workflow_orchestrator: WorkflowOrchestrator,
    ) -> None:
        self._artifact_read_model = artifact_read_model
        self._page_read_model = page_read_model
        self._compound_vector_store = compound_vector_store
        self._workflow_orchestrator = workflow_orchestrator

    async def execute(self, workspace_id: UUID) -> BulkWorkflowResponse:
        # 1. Purge stale/orphan compound vectors. Best-effort: a failure here must not
        #    block re-extraction — the cascade still rebuilds vectors for current pages.
        try:
            await self._compound_vector_store.delete_compound_embeddings_for_workspace(
                workspace_id,
            )
        except Exception:
            log.warning("bulk_reprocess_compounds.purge_failed", workspace_id=str(workspace_id))

        # 2. Enumerate all pages across the workspace's artifacts.
        artifacts = await self._artifact_read_model.list_artifacts(
            workspace_id=workspace_id,
            limit=10_000,
        )
        pages = await self._page_read_model.get_pages_by_artifact_ids(
            artifact_ids=[artifact.artifact_id for artifact in artifacts],
            workspace_id=workspace_id,
        )

        # 3. Start compound extraction per page (cascade handles re-embedding).
        workflow_ids: list[str] = []
        for page in pages:
            try:
                await self._workflow_orchestrator.start_compound_extraction_workflow(
                    page_id=page.page_id,
                )
                workflow_ids.append(f"compound-extraction-{page.page_id}")
            except Exception:
                log.warning(
                    "bulk_reprocess_compounds.page_failed",
                    page_id=str(page.page_id),
                )

        log.info(
            "bulk_reprocess_compounds.completed",
            triggered=len(workflow_ids),
            artifacts=len(artifacts),
            workspace_id=str(workspace_id),
        )

        return BulkWorkflowResponse(
            triggered=len(workflow_ids),
            workflow_ids=workflow_ids,
        )
