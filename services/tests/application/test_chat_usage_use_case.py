"""GetUserTokenUsageUseCase — per-user token totals from the usage ledger."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.chat_dtos import TokenUsageDTO
from application.use_cases.chat_use_cases import GetUserTokenUsageUseCase


class _FakeUsageStore:
    def __init__(self, usage: TokenUsageDTO | None = None, *, raises: bool = False) -> None:
        self._usage = usage or TokenUsageDTO()
        self._raises = raises
        self.calls: list[dict] = []

    async def sum_for_user(self, workspace_id, user_id, *, since=None, kind=None):
        self.calls.append(
            {"workspace_id": workspace_id, "user_id": user_id, "since": since, "kind": kind},
        )
        if self._raises:
            raise RuntimeError("boom")
        return self._usage


@pytest.mark.asyncio
async def test_returns_all_time_usage_by_default() -> None:
    usage = TokenUsageDTO(prompt=1000, completion=200, total=1200)
    store = _FakeUsageStore(usage=usage)
    ws, owner = uuid4(), uuid4()

    result = await GetUserTokenUsageUseCase(token_usage_store=store).execute(
        workspace_id=ws, owner_id=owner,
    )

    assert isinstance(result, Success)
    assert result.unwrap() == usage
    assert store.calls == [{"workspace_id": ws, "user_id": owner, "since": None, "kind": None}]


@pytest.mark.asyncio
async def test_days_window_translates_to_since() -> None:
    store = _FakeUsageStore()
    await GetUserTokenUsageUseCase(token_usage_store=store).execute(
        workspace_id=uuid4(), owner_id=uuid4(), days=30, kind="chat",
    )
    call = store.calls[0]
    assert call["kind"] == "chat"
    expected = datetime.now(UTC) - timedelta(days=30)
    assert abs((call["since"] - expected).total_seconds()) < 5


@pytest.mark.asyncio
async def test_store_error_maps_to_failure() -> None:
    store = _FakeUsageStore(raises=True)
    result = await GetUserTokenUsageUseCase(token_usage_store=store).execute(
        workspace_id=uuid4(), owner_id=uuid4(),
    )
    assert isinstance(result, Failure)
