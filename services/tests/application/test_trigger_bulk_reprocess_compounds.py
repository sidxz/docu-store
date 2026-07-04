"""Tests for TriggerBulkReprocessCompoundsUseCase."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from application.dtos.health_dtos import BulkWorkflowResponse
from application.workflow_use_cases.trigger_bulk_reprocess_compounds_use_case import (
    TriggerBulkReprocessCompoundsUseCase,
)
from tests.mocks import (
    MockArtifactReadModel,
    MockCompoundVectorStore,
    MockPageReadModel,
    MockWorkflowOrchestrator,
)


def _make(artifacts_pages: dict) -> tuple:
    """Build a use case from {artifact_id: [page_id, ...]} plus its mocks."""
    artifacts = {aid: SimpleNamespace(artifact_id=aid) for aid in artifacts_pages}
    pages = {
        pid: SimpleNamespace(page_id=pid, artifact_id=aid)
        for aid, pids in artifacts_pages.items()
        for pid in pids
    }
    compound_store = MockCompoundVectorStore()
    orchestrator = MockWorkflowOrchestrator()
    use_case = TriggerBulkReprocessCompoundsUseCase(
        artifact_read_model=MockArtifactReadModel(artifacts),
        page_read_model=MockPageReadModel(pages),
        compound_vector_store=compound_store,
        workflow_orchestrator=orchestrator,
    )
    return use_case, compound_store, orchestrator


@pytest.mark.asyncio
async def test_purges_workspace_then_starts_extraction_per_page() -> None:
    ws = uuid4()
    a1, a2 = uuid4(), uuid4()
    p1, p2, p3 = uuid4(), uuid4(), uuid4()
    use_case, compound_store, orchestrator = _make({a1: [p1, p2], a2: [p3]})

    result = await use_case.execute(workspace_id=ws)

    # Purge happened, scoped to the workspace
    assert compound_store.deleted_workspaces == [ws]
    # Extraction fired for every page (order-independent)
    assert set(orchestrator.compound_extraction_calls) == {p1, p2, p3}
    assert isinstance(result, BulkWorkflowResponse)
    assert result.triggered == 3
    assert f"compound-extraction-{p1}" in result.workflow_ids


@pytest.mark.asyncio
async def test_purge_failure_does_not_block_extraction() -> None:
    ws = uuid4()
    page = uuid4()
    use_case, _, orchestrator = _make({uuid4(): [page]})

    # Make the purge blow up — extraction must still run (best-effort cleanup).
    async def boom(_workspace_id):
        raise RuntimeError("qdrant down")

    use_case._compound_vector_store.delete_compound_embeddings_for_workspace = boom

    result = await use_case.execute(workspace_id=ws)

    assert orchestrator.compound_extraction_calls == [page]
    assert result.triggered == 1


@pytest.mark.asyncio
async def test_no_artifacts_triggers_nothing() -> None:
    use_case, compound_store, orchestrator = _make({})

    result = await use_case.execute(workspace_id=uuid4())

    assert result.triggered == 0
    assert orchestrator.compound_extraction_calls == []
    # Purge still runs (clears any orphans even with no live artifacts).
    assert len(compound_store.deleted_workspaces) == 1
