"""list_recent_conversations spans both surfaces; list_conversations still filters.

Recents used to hardcode a RESEARCH-only filter because the dashboard linked
every card into /chat. Now each card routes by its own conversation's
surface, so recents should interleave both surfaces by recency instead of
dropping literature conversations. This talks to a real Mongo (available
locally via docker-compose and in CI's mongodb service) since the behavior
under test is the query sent to Mongo, not application logic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from application.dtos.chat_dtos import ConversationDTO
from domain.value_objects.chat_surface import ChatSurface
from infrastructure.chat.mongo_chat_repository import MongoChatRepository

pytestmark = pytest.mark.integration


def _conv(cid, ws, owner, *, surface, updated_at) -> ConversationDTO:
    return ConversationDTO(
        conversation_id=cid,
        workspace_id=ws,
        owner_id=owner,
        title="t",
        created_at=updated_at,
        updated_at=updated_at,
        message_count=1,
        is_archived=False,
        surface=surface,
    )


@pytest.fixture
async def repo():
    client = AsyncIOMotorClient("mongodb://localhost:27017", serverSelectionTimeoutMS=3000)
    db_name = f"docu_store_test_{uuid4().hex[:8]}"
    try:
        await client.admin.command("ping")
    except Exception as exc:  # pragma: no cover - only hit with no local/CI Mongo
        pytest.skip(f"no Mongo reachable at localhost:27017: {exc}")
    yield MongoChatRepository(client, db_name=db_name)
    await client.drop_database(db_name)
    client.close()


async def test_recents_include_both_surfaces_ordered_by_updated_at(repo):
    ws, owner = uuid4(), uuid4()
    base = datetime(2026, 7, 1, tzinfo=UTC)
    oldest = _conv(uuid4(), ws, owner, surface=ChatSurface.RESEARCH, updated_at=base)
    middle = _conv(uuid4(), ws, owner, surface=ChatSurface.LITERATURE, updated_at=base + timedelta(hours=1))
    newest = _conv(uuid4(), ws, owner, surface=ChatSurface.RESEARCH, updated_at=base + timedelta(hours=2))
    for c in (oldest, middle, newest):
        await repo.create_conversation(c)

    result = await repo.list_recent_conversations(ws, owner, limit=10)

    assert [c.conversation_id for c in result] == [
        newest.conversation_id,
        middle.conversation_id,
        oldest.conversation_id,
    ]
    surfaces = {c.conversation_id: c.surface for c in result}
    assert surfaces[middle.conversation_id] == ChatSurface.LITERATURE
    assert surfaces[newest.conversation_id] == ChatSurface.RESEARCH


async def test_list_conversations_still_filters_by_surface(repo):
    ws, owner = uuid4(), uuid4()
    now = datetime(2026, 7, 1, tzinfo=UTC)
    research = _conv(uuid4(), ws, owner, surface=ChatSurface.RESEARCH, updated_at=now)
    literature = _conv(uuid4(), ws, owner, surface=ChatSurface.LITERATURE, updated_at=now)
    for c in (research, literature):
        await repo.create_conversation(c)

    research_only = await repo.list_conversations(ws, owner, surface=ChatSurface.RESEARCH)
    literature_only = await repo.list_conversations(ws, owner, surface=ChatSurface.LITERATURE)

    assert [c.conversation_id for c in research_only] == [research.conversation_id]
    assert [c.conversation_id for c in literature_only] == [literature.conversation_id]
