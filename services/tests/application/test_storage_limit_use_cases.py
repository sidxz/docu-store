"""Workspace storage limit: the lower of the admin's limit and the global cap."""

from __future__ import annotations

from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.errors import AppError
from application.use_cases.storage_limit_use_cases import (
    MIB,
    CheckStorageQuotaUseCase,
    effective_storage_limit,
)
from interfaces.api.routes.helpers import _map_app_error_to_http_exception

WS = uuid4()


class FakeLimitStore:
    def __init__(self, limit: int | None = None, *, error: Exception | None = None) -> None:
        self._limit = limit
        self._error = error

    async def get_limit(self, workspace_id):
        if self._error:
            raise self._error
        return self._limit


class FakeReadModel:
    def __init__(self, used: int) -> None:
        self._used = used
        self.sum_calls = 0

    async def sum_source_bytes(self, workspace_id) -> int:
        self.sum_calls += 1
        return self._used


async def _check(*, used: int, incoming: int, limit=None, cap=None, store=None):
    read_model = FakeReadModel(used)
    use_case = CheckStorageQuotaUseCase(store or FakeLimitStore(limit), read_model, cap)
    return await use_case.execute(WS, incoming), read_model


def test_effective_limit_is_the_lower_of_admin_and_cap():
    assert effective_storage_limit(500, 100) == 100
    assert effective_storage_limit(100, 500) == 100
    assert effective_storage_limit(None, 100) == 100
    assert effective_storage_limit(100, None) == 100
    assert effective_storage_limit(0, None) == 0
    assert effective_storage_limit(None, None) is None


@pytest.mark.asyncio
async def test_upload_that_exactly_fills_the_limit_is_allowed():
    result, _ = await _check(used=90, incoming=10, limit=100)
    assert isinstance(result, Success)


@pytest.mark.asyncio
async def test_upload_over_the_limit_is_refused_with_numbers():
    result, _ = await _check(used=95 * MIB, incoming=10 * MIB, limit=100 * MIB)
    assert isinstance(result, Failure)
    error = result.failure()
    assert error.category == "storage_full"
    assert "out of storage: 95.0 MB of 100.0 MB used" in error.message
    assert "this file is 10.0 MB" in error.message
    assert "ask a workspace admin to raise the limit" in error.message


@pytest.mark.asyncio
async def test_zero_limit_blocks_every_upload():
    result, _ = await _check(used=0, incoming=1, limit=0)
    assert isinstance(result, Failure)
    assert result.failure().category == "storage_full"


@pytest.mark.asyncio
async def test_usage_already_over_a_lowered_limit_blocks_uploads():
    result, _ = await _check(used=150, incoming=1, limit=100)
    assert isinstance(result, Failure)


@pytest.mark.asyncio
async def test_cap_binding_message_does_not_suggest_asking_an_admin():
    result, _ = await _check(used=int(99.5 * MIB), incoming=1 * MIB, limit=500 * MIB, cap=100 * MIB)
    assert isinstance(result, Failure)
    message = result.failure().message
    assert "of 100.0 MB used" in message
    assert "ask a workspace admin" not in message


@pytest.mark.asyncio
async def test_unlimited_skips_the_usage_query():
    result, read_model = await _check(used=10**12, incoming=10**12)
    assert isinstance(result, Success)
    assert read_model.sum_calls == 0


@pytest.mark.asyncio
async def test_quota_fails_open_when_the_store_errors():
    store = FakeLimitStore(error=RuntimeError("mongo down"))
    result, _ = await _check(used=0, incoming=1, cap=0, store=store)
    assert isinstance(result, Success)


def test_storage_full_maps_to_413():
    assert _map_app_error_to_http_exception(AppError("storage_full", "x")).status_code == 413
