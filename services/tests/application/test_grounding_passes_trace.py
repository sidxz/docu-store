"""A retry that succeeds must not erase the verdict that caused it.

The verify/refine loop yields one ``grounding_result`` per pass. The trace used to
assign the scalars on every event, so a turn the verifier rejected and the retry
rescued recorded only the rescue -- and because broadening retrieval closes the
coverage gate, the rescue is usually the gate's default-pass
(``is_grounded=True, llm_verified=False``). Nothing then said the verifier ever
objected. These drive the real ``SendMessageUseCase`` event loop, not a hand-built DTO.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from application.dtos.chat_dtos import AgentEvent, ChatMessageDTO
from application.use_cases.chat_use_cases import SendMessageUseCase


class FakeRepo:
    def __init__(self) -> None:
        self.saved: list[ChatMessageDTO] = []

    async def get_conversation(self, conversation_id, workspace_id, owner_id):
        return SimpleNamespace(conversation_id=conversation_id, title="t")

    async def append_message(self, msg):
        self.saved.append(msg)

    async def update_conversation(self, conversation_id, **kwargs):
        return None

    async def get_recent_messages(self, conversation_id, limit=10):
        return []


class FakeUsage:
    async def record(self, event):
        return None


class FakeAgent:
    """Replays a fixed event sequence, as the verify/refine loop would emit it."""

    def __init__(self, passes: list[tuple[bool, float, bool]]) -> None:
        self._passes = passes

    async def run(self, **kwargs):
        yield AgentEvent(type="token", delta="an answer")
        for is_grounded, confidence, llm_verified in self._passes:
            yield AgentEvent(
                type="grounding_result",
                grounding_is_grounded=is_grounded,
                grounding_confidence=confidence,
                grounding_llm_verified=llm_verified,
            )
        yield AgentEvent(type="done", duration_ms=1, message_id=uuid4())


def _run(passes: list[tuple[bool, float, bool]]):
    repo = FakeRepo()
    uc = SendMessageUseCase(
        chat_repository=repo,
        chat_agent=FakeAgent(passes),
        token_usage_store=FakeUsage(),
    )

    async def drive():
        async for _ in uc.execute(
            conversation_id=uuid4(),
            workspace_id=uuid4(),
            owner_id=uuid4(),
            message="q",
        ):
            pass

    asyncio.run(drive())
    assistant = [m for m in repo.saved if m.role == "assistant"]
    assert assistant, "expected the assistant message to be persisted"
    return assistant[-1].agent_trace


def test_a_rescued_retry_still_records_the_rejection() -> None:
    """Pass 1 rejected; pass 2 is the gate's default-pass. Both must survive."""
    trace = _run([(False, 0.4, True), (True, 0.1, False)])

    # The scalars stay the last pass -- what the user was actually served.
    assert trace.grounding_is_grounded is True
    assert trace.grounding_llm_verified is False

    # ...and the verifier's objection is still on the record.
    assert [p.is_grounded for p in trace.grounding_passes] == [False, True]
    assert [p.llm_verified for p in trace.grounding_passes] == [True, False]
    assert any(p.is_grounded is False for p in trace.grounding_passes)
    # confidence 0.1 == the skip path's coverage+0.1 on a zero-coverage answer.
    assert trace.grounding_passes[1].confidence == 0.1


def test_retry_count_derives_from_the_passes() -> None:
    assert _run([(True, 0.9, True)]).retry_count == 0
    assert _run([(False, 0.3, True), (True, 0.8, False)]).retry_count == 1
    three = _run([(False, 0.2, True), (False, 0.3, True), (True, 0.9, False)])
    assert three.retry_count == 2
    assert len(three.grounding_passes) == 3


def test_a_turn_that_never_verified_has_no_passes() -> None:
    trace = _run([])
    assert trace.grounding_passes == []
    assert trace.retry_count == 0
    assert trace.grounding_is_grounded is None


def test_a_final_rejection_is_recorded_as_such() -> None:
    """Exhausting retries does not force True: the last pass is whatever it was."""
    trace = _run([(False, 0.3, True), (False, 0.2, True)])
    assert trace.grounding_is_grounded is False
    assert [p.is_grounded for p in trace.grounding_passes] == [False, False]
