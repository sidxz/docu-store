"""GetUserTokenUsageUseCase — per-user token totals for the usage badge."""

from __future__ import annotations

from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.chat_dtos import TokenUsageDTO
from application.use_cases.chat_use_cases import GetUserTokenUsageUseCase


class _FakeRepo:
    def __init__(self, usage: TokenUsageDTO | None = None, *, raises: bool = False) -> None:
        self._usage = usage
        self._raises = raises
        self.calls: list[tuple] = []

    async def get_user_token_usage(self, workspace_id, owner_id) -> TokenUsageDTO:
        self.calls.append((workspace_id, owner_id))
        if self._raises:
            raise RuntimeError("boom")
        return self._usage


@pytest.mark.asyncio
async def test_returns_user_token_usage_for_owner() -> None:
    usage = TokenUsageDTO(prompt=1000, completion=200, total=1200)
    repo = _FakeRepo(usage=usage)
    ws, owner = uuid4(), uuid4()

    result = await GetUserTokenUsageUseCase(chat_repository=repo).execute(
        workspace_id=ws, owner_id=owner,
    )

    assert isinstance(result, Success)
    assert result.unwrap() == usage
    assert repo.calls == [(ws, owner)]


@pytest.mark.asyncio
async def test_repo_error_maps_to_failure() -> None:
    repo = _FakeRepo(raises=True)
    result = await GetUserTokenUsageUseCase(chat_repository=repo).execute(
        workspace_id=uuid4(), owner_id=uuid4(),
    )
    assert isinstance(result, Failure)
