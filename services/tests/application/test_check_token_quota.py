"""CheckTokenQuotaUseCase — monthly limit resolution + pre-flight gate."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.chat_dtos import TokenUsageDTO
from application.dtos.usage_dtos import TokenLimitEntry
from application.use_cases.token_limit_use_cases import (
    CheckTokenQuotaUseCase,
    effective_limit,
    utc_month_start,
)

WS, USER = uuid4(), uuid4()


class FakeLimitStore:
    """Rows keyed by user_id (None = workspace default); missing key = no row."""

    def __init__(self, rows: dict | None = None) -> None:
        self._rows = rows or {}

    async def get(self, workspace_id, user_id):
        if user_id in self._rows:
            return TokenLimitEntry(user_id=user_id, limit=self._rows[user_id])
        return None


class FakeUsageStore:
    """by_kind: per-kind totals for the month query; `total` is shorthand for all-chat."""

    def __init__(
        self,
        total: int = 0,
        *,
        by_kind: dict[str, int] | None = None,
        raises: bool = False,
    ) -> None:
        self._by_kind = by_kind if by_kind is not None else {"chat": total}
        self._raises = raises
        self.last_since = None

    async def sum_for_user_by_kind(self, workspace_id, user_id, *, since=None):
        if self._raises:
            raise RuntimeError("mongo down")
        self.last_since = since
        return {k: TokenUsageDTO(total=v) for k, v in self._by_kind.items()}


def _uc(rows: dict | None, usage: FakeUsageStore) -> CheckTokenQuotaUseCase:
    return CheckTokenQuotaUseCase(
        token_limit_store=FakeLimitStore(rows),
        token_usage_store=usage,
    )


def test_utc_month_start() -> None:
    assert utc_month_start(datetime(2026, 7, 13, 22, 5, tzinfo=UTC)) == datetime(
        2026, 7, 1, tzinfo=UTC,
    )


@pytest.mark.asyncio
async def test_no_rows_means_unlimited() -> None:
    result = await _uc(None, FakeUsageStore(total=10**12)).execute(WS, USER)
    assert isinstance(result, Success)


@pytest.mark.asyncio
async def test_under_default_limit_passes_and_windows_by_month() -> None:
    usage = FakeUsageStore(total=50)
    result = await _uc({None: 100}, usage).execute(WS, USER)
    assert isinstance(result, Success)
    assert usage.last_since == utc_month_start()


@pytest.mark.asyncio
async def test_at_limit_blocks_with_detail_message() -> None:
    result = await _uc({None: 100}, FakeUsageStore(total=100)).execute(WS, USER)
    assert isinstance(result, Failure)
    err = result.failure()
    assert err.category == "rate_limited"
    assert err.message == (
        "Monthly token limit reached: 100 of 100 tokens used. Resets on the 1st (UTC)."
    )


@pytest.mark.asyncio
async def test_override_beats_default() -> None:
    result = await _uc({None: 100, USER: 200}, FakeUsageStore(total=150)).execute(WS, USER)
    assert isinstance(result, Success)


@pytest.mark.asyncio
async def test_null_override_is_unlimited_over_finite_default() -> None:
    result = await _uc({None: 100, USER: None}, FakeUsageStore(total=10**12)).execute(WS, USER)
    assert isinstance(result, Success)


@pytest.mark.asyncio
async def test_zero_limit_blocks_immediately() -> None:
    result = await _uc({USER: 0}, FakeUsageStore(total=0)).execute(WS, USER)
    assert isinstance(result, Failure)


@pytest.mark.asyncio
async def test_fails_open_on_infrastructure_error() -> None:
    result = await _uc({None: 100}, FakeUsageStore(raises=True)).execute(WS, USER)
    assert isinstance(result, Success)


@pytest.mark.asyncio
async def test_all_kinds_count_toward_the_limit() -> None:
    """Enforcement totals every ledger kind, not just chat+ingestion."""
    usage = FakeUsageStore(by_kind={"chat": 40, "ingestion": 40, "future_lane": 40})
    result = await _uc({None: 100}, usage).execute(WS, USER)
    assert isinstance(result, Failure)


@pytest.mark.asyncio
async def test_effective_limit_resolution() -> None:
    assert await effective_limit(FakeLimitStore({USER: 5}), WS, USER) == 5
    assert await effective_limit(FakeLimitStore({None: 7}), WS, USER) == 7
    assert await effective_limit(FakeLimitStore({}), WS, USER) is None
    assert await effective_limit(FakeLimitStore({None: 7, USER: None}), WS, USER) is None
