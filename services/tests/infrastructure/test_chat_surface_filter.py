"""Conversations are listed per surface, without a backfill.

The interesting case is the conversation written before surfaces existed. Its
document has no `surface` field at all, and it must still appear in Deep
Research -- because that is where it was created, and because a migration over
every existing conversation is a poor way to pay for a sidebar filter.
"""

from __future__ import annotations

from infrastructure.chat.mongo_chat_repository import _surface_query
from domain.value_objects.chat_surface import ChatSurface


def _matches(query: dict, doc: dict) -> bool:
    """Evaluate the tiny subset of Mongo this clause uses."""
    for key, cond in query.items():
        value = doc.get(key)
        if isinstance(cond, dict) and "$ne" in cond:
            if value == cond["$ne"]:
                return False
        elif value != cond:
            return False
    return True


LEGACY = {}  # written before surfaces existed
RESEARCH = {"surface": "research"}
LITERATURE = {"surface": "literature"}


def test_research_includes_conversations_that_predate_surfaces():
    q = _surface_query(ChatSurface.RESEARCH)
    assert _matches(q, LEGACY), "a conversation with no surface is a research one"
    assert _matches(q, RESEARCH)
    assert not _matches(q, LITERATURE)


def test_literature_is_exact_and_never_claims_the_untagged():
    q = _surface_query(ChatSurface.LITERATURE)
    assert _matches(q, LITERATURE)
    assert not _matches(q, RESEARCH)
    assert not _matches(q, LEGACY), "silently adopting old conversations would be wrong"


def test_the_two_surfaces_partition_every_conversation():
    research = _surface_query(ChatSurface.RESEARCH)
    literature = _surface_query(ChatSurface.LITERATURE)
    for doc in (LEGACY, RESEARCH, LITERATURE):
        assert _matches(research, doc) != _matches(literature, doc), (
            f"{doc} must land in exactly one sidebar"
        )
