"""Workspace re-embed progress: derived from Qdrant (what is stale) + Temporal (what runs)."""

from __future__ import annotations

from uuid import uuid4

from application.dtos.workflow_dtos import TemporalWorkflowInfo
from application.workflow_use_cases.workspace_reembed_use_case import WorkspaceReEmbedUseCase

A, B = str(uuid4()), str(uuid4())


class Store:
    def __init__(self, total: int, stale: dict[str, int]) -> None:
        self.result = (total, stale)

    async def stale_vectors(self, workspace_id, model_name):
        return self.result


class Orchestrator:
    def __init__(self, statuses: dict[str, str], failure: str | None = None) -> None:
        self.statuses = statuses  # workflow id -> status; missing = NOT_FOUND
        self.failure = failure
        self.started: list[tuple[str, str]] = []

    async def get_workflow_statuses(self, workflow_ids):
        return {
            name: TemporalWorkflowInfo(workflow_id=wf, status=self.statuses.get(wf, "NOT_FOUND"))
            for name, wf in workflow_ids.items()
        }

    async def get_workflow_failure(self, workflow_id):
        return self.failure

    async def start_batch_reembed_workflow(self, artifact_id):
        self.started.append(("text", str(artifact_id)))

    async def start_batch_reembed_summaries_workflow(self, artifact_id):
        self.started.append(("summaries", str(artifact_id)))


def _use_case(text, summaries, orchestrator):
    return WorkspaceReEmbedUseCase(Store(*text), Store(*summaries), orchestrator)


async def test_done_when_nothing_is_stale() -> None:
    progress = await _use_case((10, {}), (3, {}), Orchestrator({})).progress(uuid4(), "m")
    assert (progress.state, progress.total, progress.done) == ("done", 13, 13)


async def test_running_counts_vectors_already_on_the_model() -> None:
    orchestrator = Orchestrator({f"batch-reembed-{A}": "RUNNING"})
    progress = await _use_case((10, {A: 6}), (3, {B: 1}), orchestrator).progress(uuid4(), "m")
    assert (progress.state, progress.total, progress.done) == ("running", 13, 6)


async def test_failed_carries_the_workflow_error() -> None:
    orchestrator = Orchestrator(
        {f"batch-reembed-{A}": "COMPLETED", f"batch-reembed-summaries-{B}": "FAILED"},
        failure="Incorrect API key provided",
    )
    progress = await _use_case((10, {A: 1}), (3, {B: 1}), orchestrator).progress(uuid4(), "m")
    assert progress.state == "failed"
    assert progress.error == "Incorrect API key provided"


async def test_stale_with_nothing_running_is_failed_even_when_temporal_forgot() -> None:
    """A server model change, or a failure past Temporal's retention."""
    progress = await _use_case((10, {A: 10}), (0, {}), Orchestrator({})).progress(uuid4(), "m")
    assert (progress.state, progress.done, progress.error) == ("failed", 0, None)


async def test_resume_restarts_only_stale_artifact_targets() -> None:
    orchestrator = Orchestrator({})
    started = await _use_case((10, {A: 2}), (3, {B: 1}), orchestrator).resume(uuid4(), "m")
    assert started == 2
    assert orchestrator.started == [("text", A), ("summaries", B)]
