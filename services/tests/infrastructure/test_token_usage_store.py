"""Pure-logic tests for the token usage ledger adapter (doc mapping + reshaping)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from application.dtos.usage_dtos import TokenUsageEvent
from infrastructure.read_repositories.mongo_token_usage_store import (
    _event_to_doc,
    _rows_to_members,
)


def _event(**overrides) -> TokenUsageEvent:
    base = dict(
        workspace_id=uuid4(),
        user_id=uuid4(),
        kind="chat",
        source="chat_message",
        prompt=100,
        completion=20,
        total=120,
        ref="conv-1",
        created_at=datetime(2026, 7, 13, tzinfo=UTC),
    )
    base.update(overrides)
    return TokenUsageEvent(**base)


def test_event_to_doc_stringifies_uuids_and_keeps_counts() -> None:
    ev = _event()
    doc = _event_to_doc(ev)
    assert doc["workspace_id"] == str(ev.workspace_id)
    assert doc["user_id"] == str(ev.user_id)
    assert (doc["prompt"], doc["completion"], doc["total"]) == (100, 20, 120)
    assert doc["kind"] == "chat"
    assert doc["source"] == "chat_message"
    assert "_id" not in doc  # no event_id -> Mongo assigns one


def test_event_to_doc_uses_event_id_as_mongo_id() -> None:
    doc = _event_to_doc(_event(event_id="chat:abc"))
    assert doc["_id"] == "chat:abc"


def test_event_to_doc_allows_unattributed_usage() -> None:
    doc = _event_to_doc(_event(user_id=None, workspace_id=None))
    assert doc["user_id"] is None
    assert doc["workspace_id"] is None


def test_rows_to_members_splits_kinds_and_sorts_by_total() -> None:
    rows = [
        {"_id": {"user_id": "u1", "kind": "chat"}, "prompt": 10, "completion": 5, "total": 15, "events": 2},
        {"_id": {"user_id": "u1", "kind": "ingestion"}, "prompt": 100, "completion": 0, "total": 100, "events": 1},
        {"_id": {"user_id": "u2", "kind": "chat"}, "prompt": 500, "completion": 50, "total": 550, "events": 3},
    ]
    members = _rows_to_members(rows)
    assert [m.user_id for m in members] == ["u2", "u1"]  # sorted by total desc
    u1 = members[1]
    assert u1.chat.total == 15 and u1.chat.event_count == 2
    assert u1.ingestion.total == 100 and u1.ingestion.event_count == 1
    assert u1.total_tokens == 115


def test_rows_to_members_handles_unattributed_row() -> None:
    rows = [{"_id": {"user_id": None, "kind": "ingestion"}, "prompt": 7, "completion": 0, "total": 7, "events": 1}]
    members = _rows_to_members(rows)
    assert members[0].user_id is None
    assert members[0].ingestion.total == 7
