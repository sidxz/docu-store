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
