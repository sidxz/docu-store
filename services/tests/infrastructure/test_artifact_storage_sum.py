"""Uploaded bytes per workspace, summed over the artifact read models."""

from __future__ import annotations

from uuid import uuid4

import pytest

from infrastructure.read_repositories.mongo_read_repository import MongoReadRepository


class FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    async def to_list(self, length):
        return self._docs[:length] if length else list(self._docs)


class FakeArtifacts:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def aggregate(self, pipeline):
        return FakeCursor(self._docs)


def _repo(docs: list[dict]) -> MongoReadRepository:
    repo = MongoReadRepository.__new__(MongoReadRepository)
    repo.artifacts = FakeArtifacts(docs)
    return repo


@pytest.mark.asyncio
async def test_sum_source_bytes_returns_the_total() -> None:
    assert await _repo([{"_id": None, "total": 42}]).sum_source_bytes(uuid4()) == 42


@pytest.mark.asyncio
async def test_sum_source_bytes_of_empty_workspace_is_zero() -> None:
    assert await _repo([]).sum_source_bytes(uuid4()) == 0
