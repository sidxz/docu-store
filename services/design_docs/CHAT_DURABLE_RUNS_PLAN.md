# Chat Durable Runs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chat answers survive the user navigating away, switching tabs, or reloading — generation runs to completion server-side, the UI can reattach to a live run, and the browser notifies the user when an answer is ready.

**Architecture:** An in-process `ChatRunRegistry` decouples `SendMessageUseCase` from the HTTP connection: a background asyncio task pumps agent events into a replayable, sequence-stamped SSE frame buffer; HTTP responses (the original POST and a new resume GET) are just subscribers. The frontend stops aborting the stream on unmount (the Zustand store is already global), reattaches via a new `active_run` flag, and fires native browser Notifications. Spec: `services/design_docs/CHAT_DURABLE_RUNS.md`.

**Tech Stack:** FastAPI + Starlette SSE, asyncio, lagom DI, pytest(-asyncio auto mode); Next.js 16, TanStack Query v5, Zustand, sonner, native Notifications API.

## Global Constraints

- All Python commands run via `uv run` from `/Users/sidx/workspace/docu-store/services/` (e.g. `uv run pytest`).
- All web commands run via `pnpm` from `/Users/sidx/workspace/docu-store/web/` (typecheck: `pnpm --filter portal lint` — that script is `tsc --noEmit`; there is NO frontend unit-test runner in this repo, so frontend tasks verify via typecheck + the final browser pass).
- No new dependencies, backend or frontend.
- Python style: `from __future__ import annotations`, `X | None` unions, structlog logging, pydantic v2 models.
- Commits: conventional commits (`feat(chat): …`, `test(chat): …`), each ending with the trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Work on a feature branch named `chat-durable-runs` (create it before Task 1 if not already on it).
- `SendMessageUseCase` (`application/use_cases/chat_use_cases.py`) must NOT be modified — the whole design hinges on driving it to completion from a task instead of the response.

---

### Task 1: ChatRunRegistry

**Files:**
- Create: `services/infrastructure/chat/run_registry.py`
- Test: `services/tests/infrastructure/test_chat_run_registry.py`

**Interfaces:**
- Consumes: `application.dtos.chat_dtos.AgentEvent` (existing pydantic model with `type: Literal[...]`, optional `delta`, `error_message`, etc.)
- Produces (used by Task 2):
  - `class RunAlreadyActive(Exception)`
  - `@dataclass ChatRun` with fields `run_id: UUID`, `conversation_id: UUID`, `workspace_id: UUID`, `owner_id: UUID`, `task: asyncio.Task | None`, `events: list[str]`, `subscribers: list[asyncio.Queue[str | None]]`, `done: bool`
  - `class ChatRunRegistry`:
    - `__init__(self, done_ttl_seconds: float = 60.0)`
    - `start(self, conversation_id: UUID, workspace_id: UUID, owner_id: UUID, agen: AsyncIterator[AgentEvent]) -> ChatRun` — raises `RunAlreadyActive`
    - `subscribe(self, conversation_id: UUID, after: int = -1) -> AsyncIterator[str]` (async generator of SSE frame strings)
    - `stop(self, conversation_id: UUID) -> bool`
    - `active(self, conversation_id: UUID) -> ChatRun | None`
  - `map_event_type(event_type: str) -> str` (moved here from `chat_routes.py`; Task 2 deletes the route-local copy)
  - SSE frame format: `id: <seq>\nevent: <sse_name>\ndata: <json>\n\n` where seq is 0-based per run and json is `event.model_dump(mode="json", exclude_none=True)`

- [ ] **Step 1: Write the failing tests**

Create `services/tests/infrastructure/test_chat_run_registry.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sidx/workspace/docu-store/services && uv run pytest tests/infrastructure/test_chat_run_registry.py -v`
Expected: collection error — `ModuleNotFoundError`/`ImportError` for `infrastructure.chat.run_registry`.

- [ ] **Step 3: Write the implementation**

Create `services/infrastructure/chat/run_registry.py`:

```python
"""In-process chat run registry: decouples agent generation from HTTP clients.

One run per conversation. ``start()`` pumps ``SendMessageUseCase.execute()``
events into a replayable buffer of pre-serialized SSE frames; any number of
HTTP responses subscribe (replay + live tail). The pipeline runs to
completion — and persists its assistant message — even if every subscriber
disconnects.

# ponytail: in-memory, assumes a single API replica; swap internals to Redis
# Streams if the API ever scales out. On a reattach miss the client falls
# back to refetching the persisted answer.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import structlog

from application.dtos.chat_dtos import AgentEvent

logger = structlog.get_logger()

_SSE_EVENT_NAMES = {
    "step_started": "agent_step",
    "step_completed": "agent_step",
}


def map_event_type(event_type: str) -> str:
    """Map internal event types to SSE event names."""
    return _SSE_EVENT_NAMES.get(event_type, event_type)


def _serialize_frame(seq: int, event: AgentEvent) -> str:
    data = event.model_dump(mode="json", exclude_none=True)
    return f"id: {seq}\nevent: {map_event_type(event.type)}\ndata: {json.dumps(data)}\n\n"


class RunAlreadyActive(Exception):
    """A run is already generating for this conversation."""


@dataclass
class ChatRun:
    """One in-flight (or recently finished) generation for a conversation."""

    run_id: UUID
    conversation_id: UUID
    workspace_id: UUID
    owner_id: UUID
    task: asyncio.Task | None = None
    events: list[str] = field(default_factory=list)
    subscribers: list[asyncio.Queue[str | None]] = field(default_factory=list)
    done: bool = False


class ChatRunRegistry:
    """Registry of live chat runs, keyed by conversation id."""

    def __init__(self, done_ttl_seconds: float = 60.0) -> None:
        self._runs: dict[UUID, ChatRun] = {}
        self._done_ttl = done_ttl_seconds

    def active(self, conversation_id: UUID) -> ChatRun | None:
        return self._runs.get(conversation_id)

    def start(
        self,
        conversation_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        agen: AsyncIterator[AgentEvent],
    ) -> ChatRun:
        existing = self._runs.get(conversation_id)
        if existing is not None and not existing.done:
            raise RunAlreadyActive(str(conversation_id))
        run = ChatRun(
            run_id=uuid4(),
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
        )
        self._runs[conversation_id] = run
        run.task = asyncio.create_task(self._pump(run, agen))
        return run

    async def _pump(self, run: ChatRun, agen: AsyncIterator[AgentEvent]) -> None:
        t0 = time.monotonic()
        step_count = 0
        try:
            async for event in agen:
                if event.type == "step_started":
                    step_count += 1
                self._emit(run, event)
        except asyncio.CancelledError:
            raise  # stop(): client-initiated discard
        except Exception as exc:
            logger.exception(
                "chat.run.error",
                conversation_id=str(run.conversation_id),
                error=str(exc),
            )
            self._emit(run, AgentEvent(type="error", error_message=str(exc)))
        finally:
            run.done = True
            for q in run.subscribers:
                q.put_nowait(None)
            asyncio.get_running_loop().call_later(
                self._done_ttl, self._evict, run.conversation_id, run.run_id
            )
            logger.info(
                "chat.response_completed",
                duration_ms=round((time.monotonic() - t0) * 1000, 2),
                step_count=step_count,
                conversation_id=str(run.conversation_id),
            )

    def _emit(self, run: ChatRun, event: AgentEvent) -> None:
        frame = _serialize_frame(len(run.events), event)
        run.events.append(frame)
        for q in run.subscribers:
            q.put_nowait(frame)

    def _evict(self, conversation_id: UUID, run_id: UUID) -> None:
        run = self._runs.get(conversation_id)
        if run is not None and run.run_id == run_id:
            del self._runs[conversation_id]

    async def subscribe(self, conversation_id: UUID, after: int = -1) -> AsyncIterator[str]:
        run = self._runs.get(conversation_id)
        if run is None:
            return
        # Snapshot + attach with no await in between (single event loop), so
        # no frame can fall between replay and tail; live frames land in the
        # queue even while replay yields below.
        replay = run.events[after + 1 :]
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        attached = not run.done
        if attached:
            run.subscribers.append(queue)
        try:
            for frame in replay:
                yield frame
            if not attached:
                return
            while (frame := await queue.get()) is not None:
                yield frame
        finally:
            if attached and queue in run.subscribers:
                run.subscribers.remove(queue)

    def stop(self, conversation_id: UUID) -> bool:
        run = self._runs.pop(conversation_id, None)
        if run is None:
            return False
        if run.task is not None and not run.task.done():
            run.task.cancel()
        for q in run.subscribers:
            q.put_nowait(None)
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/sidx/workspace/docu-store/services && uv run pytest tests/infrastructure/test_chat_run_registry.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/sidx/workspace/docu-store
git add services/infrastructure/chat/run_registry.py services/tests/infrastructure/test_chat_run_registry.py
git commit -m "feat(chat): in-process run registry decoupling generation from HTTP clients

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Routes — durable POST, resume GET, stop DELETE, active_run flag

**Files:**
- Modify: `services/interfaces/api/routes/chat_routes.py` (send_message ~lines 211-274, get_conversation ~lines 159-175, `_map_event_type` at bottom ~lines 302-316, imports)
- Modify: `services/application/dtos/chat_dtos.py:194-197` (`ConversationDetailDTO`)
- Modify: `services/infrastructure/di/container.py` (~line 1029, chat use-case block)
- Modify: `services/tests/interfaces/test_quota_enforcement.py:46-54` (`_client` FakeContainer mapping)
- Test: `services/tests/interfaces/test_chat_run_routes.py` (new)

**Interfaces:**
- Consumes (from Task 1): `ChatRunRegistry`, `ChatRun`, `RunAlreadyActive` from `infrastructure.chat.run_registry`; `registry.start(conversation_id, workspace_id, owner_id, agen)`, `registry.subscribe(conversation_id, after=-1)`, `registry.stop(conversation_id)`, `registry.active(conversation_id)`.
- Produces (used by Tasks 3-4 frontend):
  - `POST /chat/{id}/messages` → SSE as before, plus `id: <seq>` lines; `409` with detail `"A response is already being generated for this conversation."` when a run is active.
  - `GET /chat/{id}/messages/stream?after=<int>` → SSE replay+tail; `404` when no run (or not the caller's).
  - `DELETE /chat/{id}/run` → `204`; `404` when no run (or not the caller's).
  - `GET /chat/{id}` response gains `active_run: bool` (false once the run is done, even inside the eviction grace).

- [ ] **Step 1: Write the failing route tests**

Create `services/tests/interfaces/test_chat_run_routes.py`:

```python
"""Durable chat run routes: 409 on double send, resume replay/404, stop, active_run."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from returns.result import Success

from application.dtos.chat_dtos import AgentEvent
from application.use_cases.chat_use_cases import (
    GetConversationUseCase,
    SendMessageUseCase,
)
from application.use_cases.token_limit_use_cases import CheckTokenQuotaUseCase
from infrastructure.chat.run_registry import ChatRun, ChatRunRegistry
from interfaces.api.main import app
from interfaces.dependencies import get_auth, get_container
from tests.conftest import strip_authz_middleware
from tests.fakes.fake_auth import FakeAuth

WS = uuid4()
OWNER = uuid4()


class FakeQuota:
    async def execute(self, workspace_id, user_id):
        return Success(None)


class FakeSendUseCase:
    async def execute(self, **kwargs):
        yield AgentEvent(type="token", delta="hello")
        yield AgentEvent(type="done")


class FakeGetConversation:
    def __init__(self) -> None:
        from datetime import UTC, datetime

        from application.dtos.chat_dtos import ConversationDetailDTO

        now = datetime.now(UTC)
        self._make = lambda cid: ConversationDetailDTO(
            conversation_id=cid,
            workspace_id=WS,
            owner_id=OWNER,
            title="t",
            created_at=now,
            updated_at=now,
            message_count=0,
            messages=[],
        )

    async def execute(self, conversation_id, workspace_id, skip=0, limit=100):
        return self._make(conversation_id)


class FakeContainer:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]


def _client(registry: ChatRunRegistry) -> TestClient:
    strip_authz_middleware(app)
    app.dependency_overrides[get_container] = lambda: FakeContainer(
        {
            CheckTokenQuotaUseCase: FakeQuota(),
            SendMessageUseCase: FakeSendUseCase(),
            GetConversationUseCase: FakeGetConversation(),
            ChatRunRegistry: registry,
        },
    )
    app.dependency_overrides[get_auth] = lambda: FakeAuth(
        role="editor", user_id=OWNER, workspace_id=WS,
    )
    return TestClient(app)


def _seed_run(
    registry: ChatRunRegistry,
    cid: UUID,
    *,
    done: bool = False,
    frames: list[str] | None = None,
    workspace_id: UUID = WS,
    owner_id: UUID = OWNER,
) -> ChatRun:
    run = ChatRun(
        run_id=uuid4(),
        conversation_id=cid,
        workspace_id=workspace_id,
        owner_id=owner_id,
        done=done,
        events=frames or [],
    )
    registry._runs[cid] = run
    return run


def test_send_streams_seq_stamped_frames() -> None:
    registry = ChatRunRegistry()
    try:
        resp = _client(registry).post(f"/chat/{uuid4()}/messages", json={"message": "hi"})
        assert resp.status_code == 200
        assert "id: 0\nevent: token\n" in resp.text
        assert "id: 1\nevent: done\n" in resp.text
    finally:
        app.dependency_overrides.clear()


def test_send_conflicts_while_run_active() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    _seed_run(registry, cid, done=False)
    try:
        resp = _client(registry).post(f"/chat/{cid}/messages", json={"message": "hi"})
        assert resp.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_resume_replays_buffered_frames() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    frames = ["id: 0\nevent: token\ndata: {}\n\n", "id: 1\nevent: done\ndata: {}\n\n"]
    _seed_run(registry, cid, done=True, frames=frames)
    try:
        resp = _client(registry).get(f"/chat/{cid}/messages/stream")
        assert resp.status_code == 200
        assert resp.text == "".join(frames)
    finally:
        app.dependency_overrides.clear()


def test_resume_honors_after_offset() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    frames = ["id: 0\nevent: token\ndata: {}\n\n", "id: 1\nevent: done\ndata: {}\n\n"]
    _seed_run(registry, cid, done=True, frames=frames)
    try:
        resp = _client(registry).get(f"/chat/{cid}/messages/stream?after=0")
        assert resp.text == frames[1]
    finally:
        app.dependency_overrides.clear()


def test_resume_404_when_no_run() -> None:
    registry = ChatRunRegistry()
    try:
        resp = _client(registry).get(f"/chat/{uuid4()}/messages/stream")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_resume_404_for_other_users_run() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    _seed_run(registry, cid, done=True, owner_id=uuid4())  # someone else's run
    try:
        resp = _client(registry).get(f"/chat/{cid}/messages/stream")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_stop_cancels_active_run() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    _seed_run(registry, cid, done=False)
    try:
        resp = _client(registry).delete(f"/chat/{cid}/run")
        assert resp.status_code == 204
        assert registry.active(cid) is None
    finally:
        app.dependency_overrides.clear()


def test_stop_404_when_no_run() -> None:
    registry = ChatRunRegistry()
    try:
        resp = _client(registry).delete(f"/chat/{uuid4()}/run")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_stop_404_for_other_users_run() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    _seed_run(registry, cid, done=False, owner_id=uuid4())
    try:
        resp = _client(registry).delete(f"/chat/{cid}/run")
        assert resp.status_code == 404
        assert registry.active(cid) is not None  # untouched
    finally:
        app.dependency_overrides.clear()


def test_conversation_detail_reports_active_run() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    _seed_run(registry, cid, done=False)
    try:
        resp = _client(registry).get(f"/chat/{cid}")
        assert resp.status_code == 200
        assert resp.json()["active_run"] is True
    finally:
        app.dependency_overrides.clear()


def test_conversation_detail_active_run_false_when_done() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    _seed_run(registry, cid, done=True)  # finished, inside eviction grace
    try:
        resp = _client(registry).get(f"/chat/{cid}")
        assert resp.json()["active_run"] is False
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sidx/workspace/docu-store/services && uv run pytest tests/interfaces/test_chat_run_routes.py -v`
Expected: FAIL — 404s on the new routes, missing `active_run` key, no 409 (routes don't exist yet).

- [ ] **Step 3: Add `active_run` to the DTO**

In `services/application/dtos/chat_dtos.py`, change `ConversationDetailDTO` (line 194):

```python
class ConversationDetailDTO(ConversationDTO):
    """Conversation with its messages."""

    messages: list[ChatMessageDTO] = Field(default_factory=list)
    active_run: bool = False
```

- [ ] **Step 4: Rewrite the routes**

In `services/interfaces/api/routes/chat_routes.py`:

4a. Imports — add `HTTPException` to the fastapi import and import the registry; drop now-unused `json` and `time` if nothing else uses them (check: they are only used by the old `event_stream` and `_map_event_type`):

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
...
from infrastructure.chat.run_registry import ChatRunRegistry, RunAlreadyActive
```

4b. Add a module-level constant next to `router`:

```python
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
```

4c. Replace the whole `send_message` route (lines 211-274) with:

```python
@router.post("/{conversation_id}/messages", status_code=status.HTTP_200_OK)
async def send_message(
    conversation_id: UUID,
    request: SendMessageRequest,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> StreamingResponse:
    """Send a message and stream the agent response via SSE.

    Generation is decoupled from this connection: a background run keeps
    going (and persists its answer) even if the client disconnects. Frames
    carry ``id: <seq>`` so ``GET .../messages/stream`` can replay and tail.

    Returns a text/event-stream with the following event types:
    - agent_step: Step progress (started/completed)
    - retrieval_results: Retrieved source citations
    - token: Streaming answer tokens
    - structured_block: Rich content blocks (table, molecule, etc.)
    - done: Final event with message ID and metadata
    - error: Error event

    Raises 409 if a response is already being generated for this conversation.
    """
    await ensure_within_quota(auth, container)
    allowed_artifact_ids = await _get_allowed_artifact_ids(auth)

    use_case = container[SendMessageUseCase]
    registry = container[ChatRunRegistry]
    try:
        registry.start(
            conversation_id=conversation_id,
            workspace_id=auth.workspace_id,
            owner_id=auth.user_id,
            agen=use_case.execute(
                conversation_id=conversation_id,
                workspace_id=auth.workspace_id,
                owner_id=auth.user_id,
                message=request.message,
                allowed_artifact_ids=allowed_artifact_ids,
                mode=request.mode,
                reasoning=request.reasoning,
            ),
        )
    except RunAlreadyActive:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A response is already being generated for this conversation.",
        ) from None

    return StreamingResponse(
        registry.subscribe(conversation_id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


def _owned_run(registry: ChatRunRegistry, conversation_id: UUID, auth: RequestAuth):
    """The caller's run for this conversation, or raise 404."""
    run = registry.active(conversation_id)
    if run is None or run.workspace_id != auth.workspace_id or run.owner_id != auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active run for this conversation.",
        )
    return run


@router.get("/{conversation_id}/messages/stream", status_code=status.HTTP_200_OK)
async def resume_message_stream(
    conversation_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    after: int = -1,
) -> StreamingResponse:
    """Reattach to an in-flight (or just-finished) run: replay frames past
    ``after``, then tail live until done."""
    registry = container[ChatRunRegistry]
    _owned_run(registry, conversation_id, auth)
    return StreamingResponse(
        registry.subscribe(conversation_id, after=after),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.delete("/{conversation_id}/run", status_code=status.HTTP_204_NO_CONTENT)
async def stop_message_run(
    conversation_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Stop an in-flight run. Discards the partial answer (nothing persists);
    needed because disconnecting no longer cancels generation."""
    registry = container[ChatRunRegistry]
    _owned_run(registry, conversation_id, auth)
    registry.stop(conversation_id)
```

4d. In `get_conversation` (lines 159-175), set the flag before returning:

```python
    use_case = container[GetConversationUseCase]
    detail = await use_case.execute(
        conversation_id=conversation_id,
        workspace_id=auth.workspace_id,
        skip=skip,
        limit=limit,
    )
    run = container[ChatRunRegistry].active(conversation_id)
    detail.active_run = run is not None and not run.done
    return detail
```

4e. Delete the now-unused `_map_event_type` function at the bottom of the file (Task 1 moved the mapping into `run_registry.py`), and remove the `import json` / `import time` lines if they are now unused (verify with a grep of the file).

- [ ] **Step 5: Wire the registry into DI**

In `services/infrastructure/di/container.py`, in the chat block (next to the `SendMessageUseCase` registration at ~line 1029), add — note this registers an *instance*, which lagom treats as a singleton (required: the registry holds live process state):

```python
    container[ChatRunRegistry] = ChatRunRegistry()
```

with the import at the top of the file alongside the other infrastructure imports:

```python
from infrastructure.chat.run_registry import ChatRunRegistry
```

- [ ] **Step 6: Fix the existing quota tests' FakeContainer**

In `services/tests/interfaces/test_quota_enforcement.py`, the POST route now also looks up `ChatRunRegistry`. Add it to the mapping in `_client` (line 48):

```python
from infrastructure.chat.run_registry import ChatRunRegistry
...
    app.dependency_overrides[get_container] = lambda: FakeContainer(
        {
            CheckTokenQuotaUseCase: quota,
            SendMessageUseCase: FakeSendUseCase(),
            ChatRunRegistry: ChatRunRegistry(),
        },
    )
```

- [ ] **Step 7: Run the interface suites**

Run: `cd /Users/sidx/workspace/docu-store/services && uv run pytest tests/interfaces/test_chat_run_routes.py tests/interfaces/test_quota_enforcement.py -v`
Expected: all pass (11 new + existing quota tests).

- [ ] **Step 8: Run the full backend suite**

Run: `cd /Users/sidx/workspace/docu-store/services && uv run pytest -q`
Expected: all pass (~680; was 667 before this feature). If anything else asserted on the old SSE body format (no `id:` lines), fix that test to accept the `id: <seq>` line.

- [ ] **Step 9: Commit**

```bash
cd /Users/sidx/workspace/docu-store
git add services/interfaces/api/routes/chat_routes.py services/application/dtos/chat_dtos.py services/infrastructure/di/container.py services/tests/interfaces/
git commit -m "feat(chat): durable send + resume/stop endpoints + active_run flag

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Frontend — streams survive navigation; Stop becomes explicit

**Files:**
- Modify: `web/packages/types/src/domain/chat.ts:99-110` (`Conversation`)
- Modify: `web/apps/portal/src/components/chat/ChatPanel.tsx` (lines 48-52, 84-126, 156, 190, 274)
- Modify: `web/apps/portal/src/hooks/use-chat.ts` (`useSendMessage`, lines 202-208)

**Interfaces:**
- Consumes: `DELETE /chat/{id}/run` from Task 2; existing Zustand store (`streamingConversationId`, `finishStreaming`).
- Produces (used by Task 4): `useSendMessage` returns `{ ...mutation, abort, stop }` where `abort()` is client-only (kept for new-send teardown) and `stop()` = abort + server cancel + `finishStreaming()`.

- [ ] **Step 1: Add `active_run` to the Conversation type**

In `web/packages/types/src/domain/chat.ts`, add to the `Conversation` interface (line 99):

```ts
export interface Conversation {
  conversation_id: string;
  workspace_id: string;
  owner_id: string;
  title: string | null;
  folder_id: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
  model_used: string | null;
  is_archived: boolean;
  /** True while an answer is being generated server-side (detail endpoint only). */
  active_run?: boolean;
}
```

- [ ] **Step 2: Split stop from abort in `use-chat.ts`**

Replace the `abort` helper block (lines 202-208) with:

```ts
  /** Client-only teardown: cancel the local fetch without touching the
   *  server run (used before starting a new send — the old run keeps
   *  generating and persists server-side). */
  const abort = () => {
    abortRef.current?.abort();
    abortRef.current = null;
  };

  /** User-facing Stop: cancel locally AND cancel the server run (which
   *  discards the partial answer). */
  const stop = () => {
    abort();
    if (conversationId) {
      authFetch(`/chat/${conversationId}/run`, { method: "DELETE" }).catch(() => {});
    }
    store.finishStreaming();
  };

  return { ...mutation, abort, stop };
```

- [ ] **Step 3: ChatPanel — delete the unmount abort, gate by conversation, wire Stop**

In `web/apps/portal/src/components/chat/ChatPanel.tsx`:

3a. **Delete** lines 48-49 entirely:

```ts
  // Abort in-flight SSE stream on unmount (e.g. navigating away from chat)
  useEffect(() => () => sendMessage.abort(), []); // eslint-disable-line react-hooks/exhaustive-deps
```

(`useEffect` stays imported — it's used elsewhere in the file.)

3b. Extend the store destructure (lines 51-52) and derive a this-conversation flag. `MessageList` already guards itself via `streamBelongsHere` (`MessageList.tsx:52`), so raw props stay; the flag is for the input, badge, and sources panel:

```ts
  const { isStreaming, streamingContent, streamingSteps, streamingSources, chatMode } =
    useChatStore();
  const streamingConversationId = useChatStore((s) => s.streamingConversationId);
  // The store is global and streams now outlive their page — only treat this
  // conversation as busy when the live stream actually belongs to it.
  const streamingHere = isStreaming && streamingConversationId === conversationId;
```

3c. In the sources-panel effect (lines 84-126), scope the streaming/final branches to this conversation. Change:

```ts
    // 2. Answer complete — show only cited sources (finalSources from done event)
    if (finalSources && finalSources.length > 0) {
```
to:
```ts
    // 2. Answer complete — show only cited sources (finalSources from done event)
    if (streamingConversationId === conversationId && finalSources && finalSources.length > 0) {
```
and:
```ts
    // 3. Still streaming — show all retrieved sources
    if (isStreaming && streamingSources.length > 0) {
```
to:
```ts
    // 3. Still streaming — show all retrieved sources
    if (streamingHere && streamingSources.length > 0) {
```
and update the dependency array to include the new values:
```ts
  }, [isStreaming, streamingHere, streamingConversationId, conversationId, streamingSources, finalSources, data?.messages, doneEvent, activeSourcesMessageId, onSourcesChange]);
```

3d. Source-count badge (line 156): `const sourceCount = isStreaming ? ...` → `const sourceCount = streamingHere ? ...`.

3e. Input wiring (lines 190 and 274): change `onAbort={sendMessage.abort}` → `onAbort={sendMessage.stop}` in both places, and `disabled={isStreaming}` (line 274) → `disabled={streamingHere}`.

- [ ] **Step 4: Typecheck**

Run: `cd /Users/sidx/workspace/docu-store/web && pnpm --filter portal lint`
Expected: exits 0. (No frontend unit-test runner exists in this repo; behavior is verified in Task 6's browser pass.)

- [ ] **Step 5: Commit**

```bash
cd /Users/sidx/workspace/docu-store
git add web/packages/types/src/domain/chat.ts web/apps/portal/src/components/chat/ChatPanel.tsx web/apps/portal/src/hooks/use-chat.ts
git commit -m "feat(web): chat streams survive navigation; Stop cancels the server run

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Frontend — reattach to in-flight runs

**Files:**
- Modify: `web/apps/portal/src/lib/stores/chat-store.ts` (interface ~line 90, actions ~line 171)
- Modify: `web/apps/portal/src/hooks/use-chat.ts` (`useSendMessage`)
- Modify: `web/apps/portal/src/components/chat/ChatPanel.tsx` (reattach effect)

**Interfaces:**
- Consumes: `GET /chat/{id}/messages/stream` (Task 2), `active_run` (Tasks 2-3), `stop`/`abort` split (Task 3).
- Produces: store action `resumeStreaming(conversationId: string): void`; `useSendMessage` additionally returns `resume: () => Promise<void>` (idempotent — no-ops if this conversation is already streaming locally).

- [ ] **Step 1: Add `resumeStreaming` to the store**

In `web/apps/portal/src/lib/stores/chat-store.ts`, add to the `ChatState` interface after `startStreaming` (line 90):

```ts
  resumeStreaming: (conversationId: string) => void;
```

and the implementation after the `startStreaming` action (line 187). Identical reset except `pendingUserMessage` stays null — on reattach the user message is already persisted, and a pending bubble would double-render it:

```ts
  resumeStreaming: (conversationId) =>
    set({
      isStreaming: true,
      streamingContent: "",
      streamingSteps: [],
      streamingSources: [],
      finalSources: null,
      pendingUserMessage: null,
      streamingConversationId: conversationId,
      streamingThinkingBlocks: [],
      streamingReasoning: "",
      streamingStructuredBlocks: [],
      groundingResult: null,
      stepTimings: [],
      rawEvents: [],
      doneEvent: null,
    }),
```

- [ ] **Step 2: Add `resume()` to `useSendMessage`**

In `web/apps/portal/src/hooks/use-chat.ts`, inside `useSendMessage` after the `abortRef` declaration (line 120), add:

```ts
  const resumingRef = useRef(false);

  /** Reattach to a server-side run (after reload or a 409). Replays buffered
   *  events into the store, then tails live. Idempotent: no-ops when this
   *  conversation is already streaming locally. */
  const resume = async () => {
    if (!conversationId || resumingRef.current) return;
    const s = useChatStore.getState();
    if (s.isStreaming && s.streamingConversationId === conversationId) return;
    resumingRef.current = true;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    useChatStore.getState().resumeStreaming(conversationId);
    try {
      const res = await authFetch(`/chat/${conversationId}/messages/stream`, {
        signal: controller.signal,
      });
      // 404 = run finished (or evicted) before we attached — the refetch
      // below picks up the persisted answer.
      if (res.ok) {
        await processSSEStream(res, store, controller.signal, trackEvent);
      }
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) throw error;
    } finally {
      resumingRef.current = false;
      // A newer send/resume may have taken over the stream — only the
      // owner of the current controller may finish and refetch.
      if (abortRef.current === controller) {
        useChatStore.getState().finishStreaming();
        queryClient.invalidateQueries({ queryKey: queryKeys.chat.detail(conversationId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.chat.all });
      }
    }
  };
```

- [ ] **Step 3: Handle 409 on send by reattaching**

Still in `useSendMessage`'s `mutationFn`, in the `!res.ok` branch (lines 158-165), add a 409 case before the generic error path:

```ts
      if (!res.ok) {
        if (res.status === 409) {
          // Another client (or tab) is already generating in this
          // conversation — reattach to that run instead of erroring.
          // The message we tried to send was not accepted.
          store.finishStreaming();
          await resume();
          return;
        }
        const detail = await readErrorDetail(res);
        const message = detail ?? `Chat failed: ${res.statusText}`;
        // Render in-thread via the same path SSE error events use.
        store.appendToken(`\n\n**Error:** ${message}`);
        store.finishStreaming();
        throw new Error(message);
      }
```

and extend the hook's return to expose it:

```ts
  return { ...mutation, abort, stop, resume };
```

- [ ] **Step 4: Reattach on mount in ChatPanel**

In `web/apps/portal/src/components/chat/ChatPanel.tsx`, after the queued-message effect (line 142), add:

```ts
  // Reattach to a server-side run after a reload (or a 409): the detail
  // endpoint says one is active and no local stream owns this conversation.
  // resume() itself is idempotent, so firing on refetches is harmless.
  useEffect(() => {
    if (data?.active_run) void sendMessage.resume();
  }, [data?.active_run, conversationId]); // eslint-disable-line react-hooks/exhaustive-deps
```

- [ ] **Step 5: Typecheck**

Run: `cd /Users/sidx/workspace/docu-store/web && pnpm --filter portal lint`
Expected: exits 0.

- [ ] **Step 6: Commit**

```bash
cd /Users/sidx/workspace/docu-store
git add web/apps/portal/src/lib/stores/chat-store.ts web/apps/portal/src/hooks/use-chat.ts web/apps/portal/src/components/chat/ChatPanel.tsx
git commit -m "feat(web): reattach chat UI to in-flight server runs

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Frontend — answer-ready notifications

**Files:**
- Create: `web/apps/portal/src/components/chat/ChatNotifications.tsx`
- Modify: `web/apps/portal/src/app/[workspace]/layout.tsx` (mount next to `<AnalyticsProvider />`)

**Interfaces:**
- Consumes: Zustand store transitions (`isStreaming`, `doneEvent`, `streamingConversationId`, `streamingContent`); sonner `toast` (the `<Toaster>` is already mounted in `Providers.tsx:123`).
- Produces: `<ChatNotifications />` — null-rendering client component; must live in the workspace layout so it survives chat-route unmounts.

- [ ] **Step 1: Create the component**

Create `web/apps/portal/src/components/chat/ChatNotifications.tsx`:

```tsx
"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";
import { toast } from "sonner";
import { useChatStore } from "@/lib/stores/chat-store";

const DISMISS_KEY = "chat-notify-dismissed";
const PROMPT_AFTER_MS = 12_000;

/**
 * Null-rendering listener mounted in the workspace layout (it must outlive
 * the chat routes). Two jobs:
 * 1. When a stream drags past ~12s, offer browser notifications once.
 * 2. When an answer completes while the user is elsewhere (tab hidden or
 *    on another route), fire a native Notification that links back.
 */
export function ChatNotifications() {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const router = useRouter();
  const pathname = usePathname();
  const pathnameRef = useRef(pathname);
  pathnameRef.current = pathname;

  useEffect(() => {
    if (typeof Notification === "undefined") return; // unsupported browser
    if (!isStreaming) return;

    // Rising edge: one-time permission offer if the answer is slow.
    const timer = setTimeout(() => {
      const s = useChatStore.getState();
      if (!s.isStreaming) return;
      if (Notification.permission !== "default") return; // already granted/denied
      if (localStorage.getItem(DISMISS_KEY)) return;
      toast("Still working on your answer", {
        description: "Get a browser notification when it's ready?",
        duration: 10_000,
        action: {
          label: "Notify me",
          onClick: () => void Notification.requestPermission(),
        },
        onDismiss: () => localStorage.setItem(DISMISS_KEY, "1"),
      });
    }, PROMPT_AFTER_MS);

    // Falling edge (cleanup fires when isStreaming flips false): notify if
    // the user isn't looking. doneEvent==null means stop/abort/error — skip.
    return () => {
      clearTimeout(timer);
      const s = useChatStore.getState();
      if (s.isStreaming) return; // effect re-run/unmount, not completion
      if (!s.doneEvent) return;
      if (Notification.permission !== "granted") return;
      const convId = s.streamingConversationId;
      if (!convId) return;
      const path = pathnameRef.current ?? "";
      const viewing = !document.hidden && path.includes(`/chat/${convId}`);
      if (viewing) return;
      const workspace = path.split("/")[1] ?? "";
      const n = new Notification("Answer ready", {
        body: s.streamingContent.slice(0, 120) || "Your chat answer is ready.",
        tag: convId, // replaces stale notifications for the same conversation
      });
      n.onclick = () => {
        window.focus();
        router.push(`/${workspace}/chat/${convId}`);
        n.close();
      };
    };
  }, [isStreaming, router]);

  return null;
}
```

- [ ] **Step 2: Mount it in the workspace layout**

In `web/apps/portal/src/app/[workspace]/layout.tsx`, import and render it next to `<AnalyticsProvider />`:

```tsx
import { ChatNotifications } from "@/components/chat/ChatNotifications";
```

```tsx
    <AuthGuardWrapper>
      <AnalyticsProvider />
      <ChatNotifications />
```

- [ ] **Step 3: Typecheck**

Run: `cd /Users/sidx/workspace/docu-store/web && pnpm --filter portal lint`
Expected: exits 0.

- [ ] **Step 4: Commit**

```bash
cd /Users/sidx/workspace/docu-store
git add web/apps/portal/src/components/chat/ChatNotifications.tsx "web/apps/portal/src/app/[workspace]/layout.tsx"
git commit -m "feat(web): browser notification when a chat answer is ready

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Full-suite + runtime verification

**Files:** none (verification only).

- [ ] **Step 1: Full backend suite**

Run: `cd /Users/sidx/workspace/docu-store/services && uv run pytest -q`
Expected: all pass, 0 failures.

- [ ] **Step 2: Frontend typecheck**

Run: `cd /Users/sidx/workspace/docu-store/web && pnpm --filter portal lint`
Expected: exits 0.

- [ ] **Step 3: Runtime pass**

Use the repo's `verify` skill (backend runtime verification) to bring the stack up, then walk this checklist in the browser against the dev servers (API :8010, web :15000). Chat answers take ~1 min, which is enough time for every scenario:

1. **Navigate-away survival:** send a thinking-mode message → immediately navigate to Documents → return to the chat → the stream is still rendering live; the answer completes and persists.
2. **Reload reattach:** send a message → hard-reload mid-generation → conversation shows the user message, then the UI reattaches (steps/partial answer replay near-instantly) and tails to completion.
3. **Tab close durability:** send a message → close the tab entirely → reopen the conversation after ~90s → the full answer is there.
4. **Stop:** send a message → hit Stop → generation ends (check API logs for the cancelled run; no assistant message persisted; input re-enabled).
5. **409 path:** send a message in one tab, then send another in the same conversation from a second tab → second tab reattaches to the in-flight run instead of erroring.
6. **Notification prompt:** with browser permission unset, send a message and wait ~12s → the "Notify me" toast appears once; dismissing it is remembered (no re-prompt on the next message).
7. **Notification fire:** grant permission → send a message → switch to another tab (or another app route) → OS notification appears on completion; clicking it focuses the conversation.
8. **Cross-conversation isolation:** start a run in conversation A → open conversation B → B's input is enabled, no ghost stream renders; send in B (A's fetch drops but A's answer still persists server-side and shows on revisit).

- [ ] **Step 4: Report**

Report the checklist results to the user verbatim (pass/fail per item) before any merge/release step.
