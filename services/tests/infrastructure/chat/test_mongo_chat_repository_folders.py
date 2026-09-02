"""A folder view is not a surface view: folder listing and folder count must agree.

``list_conversations`` used to default ``surface`` to RESEARCH, so a folder
view (which calls it with no ``surface``) silently saw research-only, while
``_counts_by_folder`` never filtered by surface at all -- count 1, list empty
for a filed literature conversation. ``surface=None`` now means "all
surfaces" end to end; the sidebar keeps its separation by passing an explicit
surface. This talks to a real Mongo (available locally via docker-compose and
in CI's mongodb service) since the behavior under test is the query sent to
Mongo, not application logic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from application.dtos.chat_dtos import ChatFolderDTO, ConversationDTO
from domain.value_objects.chat_surface import ChatSurface
from infrastructure.chat.mongo_chat_repository import MongoChatRepository

pytestmark = pytest.mark.integration


def _conv(cid, ws, owner, *, surface, folder_id, updated_at) -> ConversationDTO:
    return ConversationDTO(
        conversation_id=cid,
        workspace_id=ws,
        owner_id=owner,
        title="t",
        folder_id=folder_id,
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


async def test_folder_view_with_no_surface_returns_both_surfaces(repo):
    ws, owner, folder = uuid4(), uuid4(), uuid4()
    now = datetime(2026, 7, 1, tzinfo=UTC)
    research = _conv(uuid4(), ws, owner, surface=ChatSurface.RESEARCH, folder_id=folder, updated_at=now)
    literature = _conv(uuid4(), ws, owner, surface=ChatSurface.LITERATURE, folder_id=folder, updated_at=now)
    for c in (research, literature):
        await repo.create_conversation(c)

    result = await repo.list_conversations(ws, owner, folder_id=folder)

    assert {c.conversation_id for c in result} == {research.conversation_id, literature.conversation_id}


async def test_folder_view_with_explicit_surface_still_filters(repo):
    ws, owner, folder = uuid4(), uuid4(), uuid4()
    now = datetime(2026, 7, 1, tzinfo=UTC)
    research = _conv(uuid4(), ws, owner, surface=ChatSurface.RESEARCH, folder_id=folder, updated_at=now)
    literature = _conv(uuid4(), ws, owner, surface=ChatSurface.LITERATURE, folder_id=folder, updated_at=now)
    for c in (research, literature):
        await repo.create_conversation(c)

    research_only = await repo.list_conversations(ws, owner, folder_id=folder, surface=ChatSurface.RESEARCH)

    assert [c.conversation_id for c in research_only] == [research.conversation_id]


async def test_folder_count_matches_folder_view_regardless_of_surface_mix(repo):
    """Regression test for the reported bug: tile said 1, panel showed 0.

    A folder holding only a literature conversation must report the same
    count from ``list_folders`` (which uses ``_counts_by_folder``) as the
    number of conversations ``list_conversations`` returns for it.
    """
    ws, owner, folder = uuid4(), uuid4(), uuid4()
    now = datetime(2026, 7, 1, tzinfo=UTC)
    literature = _conv(uuid4(), ws, owner, surface=ChatSurface.LITERATURE, folder_id=folder, updated_at=now)
    await repo.create_conversation(literature)
    await repo.create_folder(
        ChatFolderDTO(
            folder_id=folder,
            workspace_id=ws,
            owner_id=owner,
            name="Papers",
            created_at=now,
            updated_at=now,
        ),
    )

    folders = await repo.list_folders(ws, owner)
    listed = await repo.list_conversations(ws, owner, folder_id=folder)

    assert len(folders) == 1
    assert folders[0].chat_count == len(listed) == 1
