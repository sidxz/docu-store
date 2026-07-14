"""Pure-logic tests for MongoTokenLimitStore doc mapping (no DB)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pymongo.errors import DuplicateKeyError

from application.dtos.usage_dtos import TokenLimitEntry
from infrastructure.read_repositories.mongo_token_limit_store import (
    MongoTokenLimitStore,
    _doc_to_entry,
    _entry_doc,
)


def test_entry_doc_for_user_override() -> None:
    ws, user, admin = uuid4(), uuid4(), uuid4()
    doc = _entry_doc(ws, user, 500_000, admin)
    assert doc["workspace_id"] == str(ws)
    assert doc["user_id"] == str(user)
    assert doc["limit"] == 500_000
    assert doc["updated_by"] == str(admin)
    assert doc["updated_at"] is not None


def test_entry_doc_for_workspace_default_and_unlimited() -> None:
    doc = _entry_doc(uuid4(), None, None, uuid4())
    assert doc["user_id"] is None  # default row
    assert doc["limit"] is None  # unlimited


def test_doc_to_entry_round_trip_zero_limit() -> None:
    ws, user, admin = uuid4(), uuid4(), uuid4()
    entry = _doc_to_entry(_entry_doc(ws, user, 0, admin))
    assert entry == TokenLimitEntry(user_id=user, limit=0)


def test_doc_to_entry_default_row() -> None:
    entry = _doc_to_entry({"workspace_id": "w", "user_id": None, "limit": 123})
    assert entry.user_id is None
    assert entry.limit == 123


class _RaceyColl:
    """First upsert loses the unique-index race; the retry must succeed."""

    def __init__(self) -> None:
        self.calls = 0

    async def replace_one(self, query, doc, upsert):
        self.calls += 1
        if self.calls == 1:
            raise DuplicateKeyError("concurrent first upsert")


@pytest.mark.asyncio
async def test_set_retries_once_on_duplicate_key_race() -> None:
    store = MongoTokenLimitStore.__new__(MongoTokenLimitStore)
    store._coll = _RaceyColl()
    await store.set(uuid4(), uuid4(), 100, updated_by=uuid4())
    assert store._coll.calls == 2
