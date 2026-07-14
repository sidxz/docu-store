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
    """Returns per-kind values for month queries, a default for the main window."""

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

    async def sum_for_user(self, workspace_id, user_id, *, since=None, kind=None):
        if self._raises:
            raise RuntimeError("boom")
        self.calls.append(
            {"workspace_id": workspace_id, "user_id": user_id, "since": since, "kind": kind},
        )
        if kind in self._by_kind:
            return self._by_kind[kind]
        return self._default


class _FakeLimitStore:
    def __init__(self, rows: dict | None = None) -> None:
        self._rows = rows or {}

    async def get(self, workspace_id, user_id):
        if user_id in self._rows:
            return TokenLimitEntry(user_id=user_id, limit=self._rows[user_id])
        return None


def _uc(usage: _FakeUsageStore, rows: dict | None = None) -> GetUserTokenUsageUseCase:
    return GetUserTokenUsageUseCase(
        token_usage_store=usage, token_limit_store=_FakeLimitStore(rows),
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
    # first call = requested window (all-time), then the two month/kind calls
    assert store.calls[0] == {"workspace_id": ws, "user_id": owner, "since": None, "kind": None}
    month_calls = {(c["kind"], c["since"]) for c in store.calls[1:]}
    assert month_calls == {("chat", utc_month_start()), ("ingestion", utc_month_start())}


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
async def test_store_error_maps_to_failure() -> None:
    result = await _uc(_FakeUsageStore(raises=True)).execute(
        workspace_id=uuid4(), owner_id=uuid4(),
    )
    assert isinstance(result, Failure)
