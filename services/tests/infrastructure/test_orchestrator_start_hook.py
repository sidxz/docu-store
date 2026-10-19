"""TemporalWorkflowOrchestrator._start_workflow reports every successful start to the hook."""

from __future__ import annotations

import pytest

from infrastructure.temporal.orchestrator import TemporalWorkflowOrchestrator


class _Client:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict] = []

    async def start_workflow(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.calls.append({"args": args, **kwargs})
        if self.fail:
            raise RuntimeError("temporal down")


async def test_hook_receives_the_workflow_id_after_a_successful_start() -> None:
    orch = TemporalWorkflowOrchestrator(client=_Client())
    seen: list[str] = []

    async def hook(workflow_id: str) -> None:
        seen.append(workflow_id)

    orch.on_workflow_started = hook
    await orch._start_workflow("SomeWorkflow", "arg", id="wf-1", task_queue="q")
    assert seen == ["wf-1"]
    assert orch._client.calls[0]["id"] == "wf-1"


async def test_hook_is_skipped_when_the_start_fails() -> None:
    orch = TemporalWorkflowOrchestrator(client=_Client(fail=True))
    seen: list[str] = []

    async def hook(workflow_id: str) -> None:
        seen.append(workflow_id)

    orch.on_workflow_started = hook
    with pytest.raises(RuntimeError):
        await orch._start_workflow("SomeWorkflow", "arg", id="wf-1", task_queue="q")
    assert seen == []


async def test_no_hook_is_fine() -> None:
    orch = TemporalWorkflowOrchestrator(client=_Client())
    await orch._start_workflow("SomeWorkflow", "arg", id="wf-2", task_queue="q")


async def test_reembed_start_reports_whether_it_started() -> None:
    """Callers count re-embeds started; a refused start must not count."""
    from uuid import uuid4

    assert await TemporalWorkflowOrchestrator(client=_Client()).start_batch_reembed_workflow(
        artifact_id=uuid4()
    )
    for start in ("start_batch_reembed_workflow", "start_batch_reembed_summaries_workflow"):
        orch = TemporalWorkflowOrchestrator(client=_Client(fail=True))
        assert await getattr(orch, start)(artifact_id=uuid4()) is False


class _DescribeClient:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def get_workflow_handle(self, workflow_id, run_id=None):  # noqa: ANN001, ANN201
        return self

    async def describe(self):  # noqa: ANN201
        raise self.error


async def test_only_temporal_not_found_reads_as_not_found() -> None:
    """An outage is not "no such workflow": callers treat NOT_FOUND as finished."""
    from temporalio.service import RPCError, RPCStatusCode

    async def status(error: Exception) -> str:
        orch = TemporalWorkflowOrchestrator(client=_DescribeClient(error))
        return (await orch.get_workflow_statuses({"x": "wf"}))["x"].status

    assert await status(RPCError("gone", RPCStatusCode.NOT_FOUND, b"")) == "NOT_FOUND"
    assert await status(RPCError("down", RPCStatusCode.UNAVAILABLE, b"")) == "UNKNOWN"
