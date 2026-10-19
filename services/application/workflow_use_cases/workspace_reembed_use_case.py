"""How far a workspace is from having every vector on its current model — and resuming.

Derived from facts rather than tracked: Qdrant says which artifacts still hold
vectors from another model, Temporal says whether their re-embed workflows are
running or failed. So it also catches a re-embed that never ran (the server's
model changed) and one whose failure Temporal has long since forgotten.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Literal
from uuid import UUID

import structlog
from pydantic import BaseModel

if TYPE_CHECKING:
    from application.ports.summary_vector_store import SummaryVectorStore
    from application.ports.vector_store import VectorStore
    from application.ports.workflow_orchestrator import WorkflowOrchestrator

# target -> (orchestrator start method, workflow id pattern)
_WORKFLOWS = {
    "text": ("start_batch_reembed_workflow", "batch-reembed-{}"),
    "summaries": ("start_batch_reembed_summaries_workflow", "batch-reembed-summaries-{}"),
}
log = structlog.get_logger(__name__)

_FAILED = frozenset({"FAILED", "TIMED_OUT", "TERMINATED", "CANCELED"})


class ReEmbedProgress(BaseModel):
    # "unknown": Temporal could not be asked, so a re-embed may still be running
    state: Literal["done", "running", "failed", "unknown"]
    total: int  # vectors in the workspace
    done: int  # of those, from the current model
    error: str | None = None  # why it failed, when Temporal still knows


class WorkspaceReEmbedUseCase:
    def __init__(
        self,
        vector_store: VectorStore,
        summary_vector_store: SummaryVectorStore,
        workflow_orchestrator: WorkflowOrchestrator,
    ) -> None:
        self._vector_store = vector_store
        self._summary_vector_store = summary_vector_store
        self._orchestrator = workflow_orchestrator

    async def _stale(self, workspace_id: UUID, model_name: str) -> tuple[int, dict[str, dict]]:
        (text_total, text), (summary_total, summaries) = await asyncio.gather(
            self._vector_store.stale_vectors(workspace_id, model_name),
            self._summary_vector_store.stale_vectors(workspace_id, model_name),
        )
        return text_total + summary_total, {"text": text, "summaries": summaries}

    async def progress(self, workspace_id: UUID, model_name: str) -> ReEmbedProgress:
        total, stale = await self._stale(workspace_id, model_name)
        left = sum(sum(by_artifact.values()) for by_artifact in stale.values())
        if not left:
            return ReEmbedProgress(state="done", total=total, done=total)

        # ponytail: one describe per stale artifact and target, sequential; fine for
        # self-serve workspaces, use Temporal visibility queries if they reach thousands.
        done = total - left
        try:
            statuses = await self._orchestrator.get_workflow_statuses({
                f"{target}:{artifact_id}": _WORKFLOWS[target][1].format(artifact_id)
                for target, by_artifact in stale.items()
                for artifact_id in by_artifact
            })
        except Exception:
            log.warning("workspace_reembed.temporal_unreachable", workspace_id=str(workspace_id))
            return ReEmbedProgress(state="unknown", total=total, done=done)
        if any(s.status == "RUNNING" for s in statuses.values()):
            return ReEmbedProgress(state="running", total=total, done=done)
        if any(s.status == "UNKNOWN" for s in statuses.values()):
            return ReEmbedProgress(state="unknown", total=total, done=done)
        failed = next((s for s in statuses.values() if s.status in _FAILED), None)
        error = (
            await self._orchestrator.get_workflow_failure(failed.workflow_id, failed.run_id)
            if failed
            else None
        )
        return ReEmbedProgress(state="failed", total=total, done=done, error=error)

    async def resume(self, workspace_id: UUID, model_name: str) -> int:
        """Re-embed only the artifacts still holding vectors from another model."""
        _, stale = await self._stale(workspace_id, model_name)
        started = 0
        for target, by_artifact in stale.items():
            start = getattr(self._orchestrator, _WORKFLOWS[target][0])
            for artifact_id in by_artifact:
                started += await start(artifact_id=UUID(artifact_id))  # False: already running
        return started
