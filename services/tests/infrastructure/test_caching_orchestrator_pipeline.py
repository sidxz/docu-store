"""CachingWorkflowOrchestrator.get_artifact_pipeline_statuses: cache-first, Temporal for the rest."""

from __future__ import annotations

from uuid import uuid4

from application.dtos.workflow_dtos import TemporalWorkflowInfo
from infrastructure.temporal.caching_orchestrator import CachingWorkflowOrchestrator


class FakeCache:
    def __init__(self, cached: dict) -> None:
        self.cached = cached
        self.upserts: list = []

    async def get_cached_statuses(self, workflow_ids: dict) -> dict:
        return {n: self.cached[n] for n in workflow_ids if n in self.cached}

    async def bulk_upsert_statuses(self, entries: list) -> None:
        self.upserts.extend(entries)


class FakeInner:
    def __init__(self, live: dict) -> None:
        self.live = live
        self.asked: list[dict] = []

    async def get_workflow_statuses(self, workflow_ids: dict) -> dict:
        self.asked.append(dict(workflow_ids))
        return {
            n: self.live.get(n, TemporalWorkflowInfo(workflow_id=wid, status="NOT_FOUND"))
            for n, wid in workflow_ids.items()
        }


async def test_terminal_cached_statuses_skip_temporal_and_live_ones_write_through() -> None:
    a, p = uuid4(), uuid4()
    cache = FakeCache(
        {
            "parse": TemporalWorkflowInfo(workflow_id="pw", status="COMPLETED", from_cache=True),
            f"ner:{p}": TemporalWorkflowInfo(workflow_id="nw", status="RUNNING", from_cache=True),
        },
    )
    inner = FakeInner({f"ner:{p}": TemporalWorkflowInfo(workflow_id="nw", status="COMPLETED")})
    orch = CachingWorkflowOrchestrator(inner=inner, cache=cache)

    out = await orch.get_artifact_pipeline_statuses(a, [p])

    assert len(inner.asked) == 1
    assert "parse" not in inner.asked[0]  # terminal → served from cache
    assert f"ner:{p}" in inner.asked[0]  # cached RUNNING is re-described
    assert out["parse"].from_cache is True
    assert out[f"ner:{p}"].status == "COMPLETED"
    assert any(name == f"ner:{p}" for name, *_ in cache.upserts)  # write-through
    assert len(out) == 6 + 7


async def test_cache_read_failure_falls_back_to_temporal() -> None:
    class BrokenCache(FakeCache):
        async def get_cached_statuses(self, workflow_ids: dict) -> dict:
            raise RuntimeError("mongo down")

    inner = FakeInner({})
    orch = CachingWorkflowOrchestrator(inner=inner, cache=BrokenCache({}))
    out = await orch.get_artifact_pipeline_statuses(uuid4(), [])
    assert len(inner.asked[0]) == 6 and all(i.status == "NOT_FOUND" for i in out.values())


async def test_starting_a_workflow_forgets_its_cached_status() -> None:
    """Workflow ids are reused on re-run, so a cached FAILED must not outlive a restart."""

    class ForgettingCache(FakeCache):
        def __init__(self) -> None:
            super().__init__({})
            self.deleted: list[list[str]] = []

        async def delete_statuses(self, workflow_ids: list[str]) -> None:
            self.deleted.append(list(workflow_ids))

    class HookedInner(FakeInner):
        on_workflow_started = None

    inner, cache = HookedInner({}), ForgettingCache()
    CachingWorkflowOrchestrator(inner=inner, cache=cache)
    assert inner.on_workflow_started is not None  # wrapper subscribed to starts
    await inner.on_workflow_started("doc-metadata-abc")
    assert cache.deleted == [["doc-metadata-abc"]]
