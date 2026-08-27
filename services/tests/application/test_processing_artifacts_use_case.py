"""ListProcessingArtifactsUseCase — rows for the topbar 'documents being processed' badge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from application.dtos.artifact_dtos import ArtifactResponse
from application.dtos.workflow_dtos import TemporalWorkflowInfo
from application.use_cases.processing_artifacts_use_case import (
    GRACE,
    ListProcessingArtifactsUseCase,
    summarize,
)
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType

NOW = datetime(2026, 8, 27, 16, 0, tzinfo=UTC)


def _wf(status: str, closed_ago: timedelta | None = None) -> TemporalWorkflowInfo:
    return TemporalWorkflowInfo(
        workflow_id="x", status=status, closed_at=(NOW - closed_ago) if closed_ago else None,
    )


def test_running_parse_is_parsing_with_zero_percent() -> None:
    s = {"parse": _wf("RUNNING"), "doc_metadata": _wf("NOT_FOUND"), "ner:p1": _wf("NOT_FOUND")}
    row = summarize(uuid4(), "a.pdf", s, NOW)
    assert (row.total, row.completed, row.running, row.failed, row.percent) == (1, 0, 1, 0, 0)
    assert row.stage == "parsing" and row.active is True


def test_percent_and_stage_priority() -> None:
    s = {
        "parse": _wf("COMPLETED", timedelta(seconds=30)),
        "ner:p1": _wf("COMPLETED", timedelta(seconds=10)),
        "embedding:p1": _wf("RUNNING"),
        "tag_aggregation": _wf("RUNNING"),
    }
    row = summarize(uuid4(), "a.pdf", s, NOW)
    assert (row.total, row.completed, row.percent) == (4, 2, 50)
    assert row.stage == "indexing"  # indexing outranks finishing


def test_structure_extraction_is_its_own_stage() -> None:
    s = {"parse": _wf("COMPLETED", timedelta(seconds=30)), "compound_extraction:p1": _wf("RUNNING")}
    assert summarize(uuid4(), "a.pdf", s, NOW).stage == "extracting_structures"
    # content extraction outranks it when both run
    s["ner:p1"] = _wf("RUNNING")
    assert summarize(uuid4(), "a.pdf", s, NOW).stage == "extracting"


def test_all_done_stays_active_during_grace_then_drops() -> None:
    s = {"parse": _wf("COMPLETED", timedelta(seconds=10)), "ner:p1": _wf("COMPLETED", timedelta(seconds=5))}
    row = summarize(uuid4(), "a.pdf", s, NOW)
    assert row.percent == 100 and row.running == 0 and row.active is True and row.stage == "finishing"
    old = {k: _wf("COMPLETED", GRACE + timedelta(seconds=1)) for k in s}
    assert summarize(uuid4(), "a.pdf", old, NOW).active is False


def test_failed_counts_stage_and_last_activity() -> None:
    s = {"parse": _wf("COMPLETED", timedelta(hours=1)), "ner:p1": _wf("FAILED", timedelta(hours=1))}
    row = summarize(uuid4(), "a.pdf", s, NOW)
    assert row.failed == 1 and row.stage == "failed" and row.active is False
    assert row.last_activity_at == NOW - timedelta(hours=1)


def test_naive_closed_at_is_treated_as_utc() -> None:
    naive = (NOW - timedelta(seconds=5)).replace(tzinfo=None)
    s = {"parse": TemporalWorkflowInfo(workflow_id="x", status="COMPLETED", closed_at=naive)}
    assert summarize(uuid4(), "a.pdf", s, NOW).active is True


class FakeReadModel:
    def __init__(self, artifacts: list[ArtifactResponse]) -> None:
        self.artifacts = artifacts
        self.calls: list[dict] = []

    async def list_artifacts(self, **kw):  # noqa: ANN003
        self.calls.append(kw)
        return self.artifacts


class FakeOrchestrator:
    def __init__(self, by_artifact: dict) -> None:
        self.by_artifact = by_artifact
        self.calls: list[tuple] = []

    async def get_artifact_pipeline_statuses(self, artifact_id, page_ids):  # noqa: ANN001
        self.calls.append((artifact_id, list(page_ids)))
        return self.by_artifact.get(artifact_id, {})


def _artifact(owner, pages=()) -> ArtifactResponse:  # noqa: ANN001
    return ArtifactResponse(
        artifact_id=uuid4(),
        source_uri=None,
        source_filename="d.pdf",
        artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF,
        storage_location="/s",
        owner_id=owner,
        pages=list(pages),
    )


async def test_execute_keeps_only_my_active_or_recently_failed_documents() -> None:
    me, other = uuid4(), uuid4()
    p1 = uuid4()
    running, done, failed_old, theirs = _artifact(me, [p1]), _artifact(me), _artifact(me), _artifact(other)
    orch = FakeOrchestrator(
        {
            running.artifact_id: {
                "parse": _wf("COMPLETED", timedelta(minutes=5)),
                f"ner:{p1}": _wf("RUNNING"),
            },
            done.artifact_id: {"parse": _wf("COMPLETED", timedelta(hours=3))},
            failed_old.artifact_id: {"parse": _wf("FAILED", timedelta(days=2))},
            theirs.artifact_id: {"parse": _wf("RUNNING")},
        },
    )
    read_model = FakeReadModel([running, done, failed_old, theirs])
    uc = ListProcessingArtifactsUseCase(artifact_read_model=read_model, orchestrator=orch)

    rows = await uc.execute(workspace_id=uuid4(), user_id=me, allowed_artifact_ids=None, now=NOW)

    assert [r.artifact_id for r in rows] == [str(running.artifact_id)]
    assert (running.artifact_id, [p1]) in orch.calls
    assert all(c[0] != theirs.artifact_id for c in orch.calls)  # other users' docs never described
    assert read_model.calls[0]["sort_by"] == "updated_at"


async def test_recent_failure_is_reported_even_when_idle() -> None:
    me = uuid4()
    failed = _artifact(me)
    orch = FakeOrchestrator({failed.artifact_id: {"parse": _wf("FAILED", timedelta(hours=1))}})
    uc = ListProcessingArtifactsUseCase(artifact_read_model=FakeReadModel([failed]), orchestrator=orch)
    rows = await uc.execute(workspace_id=uuid4(), user_id=me, allowed_artifact_ids=None, now=NOW)
    assert len(rows) == 1 and rows[0].stage == "failed"
