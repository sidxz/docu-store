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


class RunAlreadyActiveError(Exception):
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
            raise RunAlreadyActiveError(str(conversation_id))
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
