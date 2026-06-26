from __future__ import annotations

import pytest

from infrastructure.llm import reasoning_context


@pytest.mark.asyncio
async def test_execute_sets_and_resets_override() -> None:
    # A minimal stand-in: the use case must set the override before running the
    # agent and reset it after. We assert the override is visible "during" and
    # cleared "after" by inspecting it from a fake agent.
    from application.use_cases.chat_use_cases import SendMessageUseCase

    seen_during: list[str | None] = []

    class _FakeRepo:
        async def get_conversation(self, *a, **k):
            class C: title = "t"
            return C()
        async def append_message(self, *a, **k): ...
        async def update_conversation(self, *a, **k): ...
        async def get_recent_messages(self, *a, **k): return []

    class _FakeAgent:
        async def run(self, **kwargs):
            seen_during.append(reasoning_context.get_lane_override("synthesis"))
            if False:
                yield  # make it an async generator
            return

    uc = object.__new__(SendMessageUseCase)
    uc._repo = _FakeRepo()
    uc._agent = _FakeAgent()

    from uuid import uuid4
    async for _ in uc.execute(
        conversation_id=uuid4(), workspace_id=uuid4(), owner_id=uuid4(),
        message="hi", reasoning={"synthesis": "high"},
    ):
        pass

    assert seen_during == ["high"]
    assert reasoning_context.get_lane_override("synthesis") is None  # reset after
