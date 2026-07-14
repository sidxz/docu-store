"""Use cases for admin-configured monthly token limits."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import structlog
from returns.result import Failure, Result, Success

from application.dtos.chat_dtos import TokenUsageDTO
from application.dtos.errors import AppError
from application.ports.token_limit_store import TokenLimitStore
from application.ports.token_usage_store import TokenUsageStore

log = structlog.get_logger(__name__)


def utc_month_start(now: datetime | None = None) -> datetime:
    """First instant of the current calendar month, UTC — limits reset on the 1st."""
    now = now or datetime.now(UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC)


async def effective_limit(
    store: TokenLimitStore,
    workspace_id: UUID,
    user_id: UUID,
) -> int | None:
    """Resolve a user's monthly token limit: override ?? workspace default ?? unlimited.

    An existing override row with limit=None makes that user explicitly unlimited,
    even over a finite workspace default.
    """
    override, default = await asyncio.gather(
        store.get(workspace_id, user_id),
        store.get(workspace_id, None),
    )
    if override is not None:
        return override.limit
    return default.limit if default is not None else None


async def month_usage_by_kind(
    usage_store: TokenUsageStore,
    workspace_id: UUID,
    user_id: UUID,
) -> dict[str, TokenUsageDTO]:
    """Current-calendar-month usage per kind — THE quota window.

    Enforcement compares the total across ALL kinds; display breaks it down.
    Both must read from here so they can't diverge on window or kind filter.
    """
    return await usage_store.sum_for_user_by_kind(
        workspace_id, user_id, since=utc_month_start(),
    )


def month_total(by_kind: dict[str, TokenUsageDTO]) -> int:
    """What enforcement counts: every kind in the ledger, not just chat+ingestion."""
    return sum(u.total for u in by_kind.values())


class CheckTokenQuotaUseCase:
    """Pre-flight monthly quota gate for chat send and document upload/create.

    Soft ceiling: compares already-recorded ledger usage, so concurrent in-flight
    requests can overshoot slightly. Fails open on infrastructure errors — a
    broken limits/ledger read must not take chat down.
    """

    def __init__(
        self,
        token_limit_store: TokenLimitStore,
        token_usage_store: TokenUsageStore,
    ) -> None:
        self._limits = token_limit_store
        self._usage = token_usage_store

    async def execute(self, workspace_id: UUID, user_id: UUID) -> Result[None, AppError]:
        try:
            limit = await effective_limit(self._limits, workspace_id, user_id)
            if limit is None:
                return Success(None)
            total = month_total(await month_usage_by_kind(self._usage, workspace_id, user_id))
            if total >= limit:
                return Failure(
                    AppError(
                        "rate_limited",
                        f"Monthly token limit reached: {total:,} of {limit:,} "
                        "tokens used. Resets on the 1st (UTC).",
                    ),
                )
            return Success(None)
        except Exception as e:
            log.warning("quota.check_failed", error=str(e), exc_info=True)
            return Success(None)
