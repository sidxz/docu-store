"""GetUserTokenUsageUseCase — windowed totals + current-month block with limit."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.chat_dtos import TokenUsageDTO
from application.dtos.usage_dtos import TokenLimitEntry
from application.use_cases.chat_use_cases import GetUserTokenUsageUseCase
from application.use_cases.token_limit_use_cases import utc_month_start


class _FakeUsageStore:
    """Windowed sum for the main query; per-kind dict for the month query."""

    def __init__(
        self,
        default: TokenUsageDTO | None = None,
        by_kind: dict[str, TokenUsageDTO] | None = None,
        *,
        raises: bool = False,
    ) -> None:
        self._default = default or TokenUsageDTO()
        self._by_kind = by_kind or {}
        self._raises = raises
        self.calls: list[dict] = []
        self.by_kind_calls: list[dict] = []

    async def sum_for_user(self, workspace_id, user_id, *, since=None, kind=None):
        if self._raises:
            raise RuntimeError("boom")
        self.calls.append(
            {"workspace_id": workspace_id, "user_id": user_id, "since": since, "kind": kind},
        )
        return self._default

    async def sum_for_user_by_kind(self, workspace_id, user_id, *, since=None):
        if self._raises:
            raise RuntimeError("boom")
        self.by_kind_calls.append(
            {"workspace_id": workspace_id, "user_id": user_id, "since": since},
        )
        return self._by_kind


class _FakeLimitStore:
    def __init__(self, rows: dict | None = None, *, raises: bool = False) -> None:
        self._rows = rows or {}
        self._raises = raises

    async def get(self, workspace_id, user_id):
        if self._raises:
            raise RuntimeError("limits down")
        if user_id in self._rows:
            return TokenLimitEntry(user_id=user_id, limit=self._rows[user_id])
        return None


def _uc(
    usage: _FakeUsageStore,
    rows: dict | None = None,
    *,
    limits_raise: bool = False,
) -> GetUserTokenUsageUseCase:
    return GetUserTokenUsageUseCase(
        token_usage_store=usage,
        token_limit_store=_FakeLimitStore(rows, raises=limits_raise),
    )


@pytest.mark.asyncio
async def test_returns_all_time_usage_plus_month_block() -> None:
    store = _FakeUsageStore(
        default=TokenUsageDTO(prompt=1000, completion=200, total=1200),
        by_kind={
            "chat": TokenUsageDTO(total=300),
            "ingestion": TokenUsageDTO(total=100),
        },
    )
    ws, owner = uuid4(), uuid4()

    result = await _uc(store, rows={None: 5000}).execute(workspace_id=ws, owner_id=owner)

    assert isinstance(result, Success)
    body = result.unwrap()
    assert (body.prompt, body.completion, body.total) == (1000, 200, 1200)
    assert body.month.chat == 300
    assert body.month.ingestion == 100
    assert body.month.total == 400
    assert body.month.limit == 5000
    assert store.calls == [{"workspace_id": ws, "user_id": owner, "since": None, "kind": None}]
    assert store.by_kind_calls == [
        {"workspace_id": ws, "user_id": owner, "since": utc_month_start()},
    ]


@pytest.mark.asyncio
async def test_month_total_counts_every_kind() -> None:
    """Display total matches enforcement: all ledger kinds, not just chat+ingestion."""
    store = _FakeUsageStore(
        by_kind={
            "chat": TokenUsageDTO(total=300),
            "ingestion": TokenUsageDTO(total=100),
            "future_lane": TokenUsageDTO(total=50),
        },
    )
    result = await _uc(store).execute(workspace_id=uuid4(), owner_id=uuid4())
    assert result.unwrap().month.total == 450


@pytest.mark.asyncio
async def test_days_window_translates_to_since() -> None:
    store = _FakeUsageStore()
    await _uc(store).execute(workspace_id=uuid4(), owner_id=uuid4(), days=30, kind="chat")
    call = store.calls[0]
    assert call["kind"] == "chat"
    expected = datetime.now(UTC) - timedelta(days=30)
    assert abs((call["since"] - expected).total_seconds()) < 5


@pytest.mark.asyncio
async def test_no_limit_rows_means_null_limit() -> None:
    result = await _uc(_FakeUsageStore()).execute(workspace_id=uuid4(), owner_id=uuid4())
    assert result.unwrap().month.limit is None


@pytest.mark.asyncio
async def test_exempt_caller_gets_no_limit() -> None:
    """Admins bypass enforcement, so the response must not render one."""
    result = await _uc(_FakeUsageStore(), rows={None: 5000}).execute(
        workspace_id=uuid4(), owner_id=uuid4(), exempt=True,
    )
    assert result.unwrap().month.limit is None


@pytest.mark.asyncio
async def test_limits_read_failure_degrades_to_null_limit() -> None:
    """A broken limits store must not 500 the ledger totals (fail soft, like the gate)."""
    result = await _uc(_FakeUsageStore(), limits_raise=True).execute(
        workspace_id=uuid4(), owner_id=uuid4(),
    )
    assert isinstance(result, Success)
    assert result.unwrap().month.limit is None


@pytest.mark.asyncio
async def test_store_error_maps_to_failure() -> None:
    result = await _uc(_FakeUsageStore(raises=True)).execute(
        workspace_id=uuid4(), owner_id=uuid4(),
    )
    assert isinstance(result, Failure)
