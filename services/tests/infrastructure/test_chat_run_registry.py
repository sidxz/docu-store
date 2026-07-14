"""ChatRunRegistry: durable pump, replay+tail subscribe, stop, eviction."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from application.dtos.chat_dtos import AgentEvent
from infrastructure.chat.run_registry import (
    ChatRunRegistry,
    RunAlreadyActive,
)

WS = uuid4()
OWNER = uuid4()


def make_agen(events: list[AgentEvent], gate: asyncio.Event | None = None):
    """Async generator yielding events; optionally waits on gate before the last one."""

    async def agen():
        for i, e in enumerate(events):
            if gate is not None and i == len(events) - 1:
                await gate.wait()
            yield e

    return agen()


def token(text: str) -> AgentEvent:
    return AgentEvent(type="token", delta=text)


DONE = AgentEvent(type="done")


async def collect(aiter) -> list[str]:
    return [frame async for frame in aiter]


async def test_pump_runs_to_completion_without_subscribers():
    """Core durability: nobody listening, the run still completes."""
    reg = ChatRunRegistry()
    cid = uuid4()
    run = reg.start(cid, WS, OWNER, make_agen([token("hi"), DONE]))
    await run.task
    assert run.done is True
    assert len(run.events) == 2


async def test_frame_format_and_event_name_mapping():
    reg = ChatRunRegistry()
    cid = uuid4()
    run = reg.start(cid, WS, OWNER, make_agen([AgentEvent(type="step_started", step="planning")]))
    await run.task
    frame = run.events[0]
    assert frame.startswith("id: 0\n")
    assert "event: agent_step\n" in frame  # step_started maps to agent_step
    assert frame.endswith("\n\n")
    assert '"step": "planning"' in frame


async def test_subscribe_after_done_replays_and_terminates():
    reg = ChatRunRegistry()
    cid = uuid4()
    run = reg.start(cid, WS, OWNER, make_agen([token("a"), token("b"), DONE]))
    await run.task
    frames = await collect(reg.subscribe(cid))
    assert len(frames) == 3
    assert frames[0].startswith("id: 0\n")
    assert frames[2].startswith("id: 2\n")


async def test_after_offset_skips_replayed_frames():
    reg = ChatRunRegistry()
    cid = uuid4()
    run = reg.start(cid, WS, OWNER, make_agen([token("a"), token("b"), DONE]))
    await run.task
    frames = await collect(reg.subscribe(cid, after=1))
    assert len(frames) == 1
    assert frames[0].startswith("id: 2\n")


async def test_live_subscriber_gets_replay_then_tail():
    reg = ChatRunRegistry()
    cid = uuid4()
    gate = asyncio.Event()
    reg.start(cid, WS, OWNER, make_agen([token("early"), DONE], gate=gate))
    await asyncio.sleep(0.01)  # let the pump emit the first frame
    collector = asyncio.ensure_future(collect(reg.subscribe(cid)))
    await asyncio.sleep(0.01)  # subscriber attached mid-run
    gate.set()
    frames = await asyncio.wait_for(collector, timeout=1)
    assert len(frames) == 2  # replayed "early" + tailed done


async def test_subscribe_unknown_conversation_yields_nothing():
    reg = ChatRunRegistry()
    frames = await collect(reg.subscribe(uuid4()))
    assert frames == []


async def test_duplicate_start_raises():
    reg = ChatRunRegistry()
    cid = uuid4()
    gate = asyncio.Event()
    reg.start(cid, WS, OWNER, make_agen([DONE], gate=gate))
    with pytest.raises(RunAlreadyActive):
        reg.start(cid, WS, OWNER, make_agen([DONE]))
    gate.set()


async def test_start_after_done_replaces_run():
    """A finished run inside its eviction grace must not block the next message."""
    reg = ChatRunRegistry()
    cid = uuid4()
    run1 = reg.start(cid, WS, OWNER, make_agen([DONE]))
    await run1.task
    run2 = reg.start(cid, WS, OWNER, make_agen([token("x"), DONE]))
    await run2.task
    assert reg.active(cid) is run2


async def test_stop_cancels_task_and_evicts():
    reg = ChatRunRegistry()
    cid = uuid4()
    gate = asyncio.Event()  # never set: run would hang forever
    run = reg.start(cid, WS, OWNER, make_agen([token("a"), DONE], gate=gate))
    await asyncio.sleep(0.01)
    collector = asyncio.ensure_future(collect(reg.subscribe(cid)))
    await asyncio.sleep(0.01)
    assert reg.stop(cid) is True
    frames = await asyncio.wait_for(collector, timeout=1)  # sentinel ends subscriber
    assert len(frames) == 1  # only the pre-stop frame
    assert reg.active(cid) is None
    with pytest.raises(asyncio.CancelledError):
        await run.task


async def test_stop_unknown_conversation_returns_false():
    assert ChatRunRegistry().stop(uuid4()) is False


async def test_pipeline_exception_emits_error_frame():
    async def boom():
        yield token("partial")
        raise RuntimeError("llm exploded")

    reg = ChatRunRegistry()
    cid = uuid4()
    run = reg.start(cid, WS, OWNER, boom())
    await run.task
    assert run.done is True
    assert "event: error\n" in run.events[-1]
    assert "llm exploded" in run.events[-1]


async def test_evicted_after_ttl():
    reg = ChatRunRegistry(done_ttl_seconds=0.02)
    cid = uuid4()
    run = reg.start(cid, WS, OWNER, make_agen([DONE]))
    await run.task
    assert reg.active(cid) is not None  # grace window
    await asyncio.sleep(0.1)
    assert reg.active(cid) is None
