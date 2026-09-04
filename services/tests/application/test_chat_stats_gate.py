from __future__ import annotations

import pytest

from infrastructure.llm import stats_context


@pytest.mark.asyncio
async def test_stats_is_forced_off_outside_literature_mode() -> None:
    # The client's statsOn flag is shared across surfaces (see Task 4 review);
    # a turn in "thinking" mode must never see stats_enabled() true, even when
    # the caller asks for it.
    from application.use_cases.chat_use_cases import SendMessageUseCase

    seen_during: list[bool] = []

    class _FakeRepo:
        async def get_conversation(self, *a, **k):
            class C:
                title = "t"

            return C()

        async def append_message(self, *a, **k): ...
        async def update_conversation(self, *a, **k): ...
        async def get_recent_messages(self, *a, **k):
            return []

    class _FakeAgent:
        async def run(self, **kwargs):
            seen_during.append(stats_context.stats_enabled())
            if False:
                yield  # make it an async generator
            return

    class _FakeUsageStore:
        async def record(self, event) -> None:  # pragma: no cover - never hit at zero usage
            return None

    uc = SendMessageUseCase(
        chat_repository=_FakeRepo(),
        chat_agent=_FakeAgent(),
        token_usage_store=_FakeUsageStore(),
    )

    from uuid import uuid4

    async for _ in uc.execute(
        conversation_id=uuid4(),
        workspace_id=uuid4(),
        owner_id=uuid4(),
        message="hi",
        mode="thinking",
        stats=True,
    ):
        pass

    assert seen_during == [False]
    assert stats_context.stats_enabled() is False


@pytest.mark.asyncio
async def test_stats_is_enabled_in_literature_mode_and_reset_after() -> None:
    from application.use_cases.chat_use_cases import SendMessageUseCase

    seen_during: list[bool] = []

    class _FakeRepo:
        async def get_conversation(self, *a, **k):
            class C:
                title = "t"

            return C()

        async def append_message(self, *a, **k): ...
        async def update_conversation(self, *a, **k): ...
        async def get_recent_messages(self, *a, **k):
            return []

    class _FakeAgent:
        async def run(self, **kwargs):
            seen_during.append(stats_context.stats_enabled())
            if False:
                yield  # make it an async generator
            return

    class _FakeUsageStore:
        async def record(self, event) -> None:  # pragma: no cover - never hit at zero usage
            return None

    uc = SendMessageUseCase(
        chat_repository=_FakeRepo(),
        chat_agent=_FakeAgent(),
        token_usage_store=_FakeUsageStore(),
    )

    from uuid import uuid4

    async for _ in uc.execute(
        conversation_id=uuid4(),
        workspace_id=uuid4(),
        owner_id=uuid4(),
        message="hi",
        mode="literature",
        stats=True,
    ):
        pass

    assert seen_during == [True]
    assert stats_context.stats_enabled() is False  # reset after the turn
