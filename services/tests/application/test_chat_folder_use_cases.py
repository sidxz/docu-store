"""Chat folder move + delete-cascade orchestration.

Covers the non-trivial branches of SetConversationFolderUseCase (bumps the
right folder dates, leaves the conversation's own date alone, validates the
destination) and DeleteFolderUseCase (unfiles chats before deleting).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pymongo.errors import DuplicateKeyError
from returns.result import Failure, Success

from application.dtos.chat_dtos import ChatFolderDTO, ConversationDTO
from application.use_cases.chat_folder_use_cases import (
    CreateFolderUseCase,
    DeleteFolderUseCase,
    SetConversationFolderUseCase,
)

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _conv(owner: UUID, ws: UUID, folder_id: UUID | None = None) -> ConversationDTO:
    return ConversationDTO(
        conversation_id=uuid4(),
        workspace_id=ws,
        owner_id=owner,
        folder_id=folder_id,
        created_at=_T0,
        updated_at=_T0,
    )


def _folder(owner: UUID, ws: UUID) -> ChatFolderDTO:
    return ChatFolderDTO(
        folder_id=uuid4(),
        workspace_id=ws,
        owner_id=owner,
        name="F",
        created_at=_T0,
        updated_at=_T0,
    )


class _FakeRepo:
    def __init__(self) -> None:
        self.conversations: dict[UUID, ConversationDTO] = {}
        self.folders: dict[UUID, ChatFolderDTO] = {}
        self.touched: list[list[UUID]] = []
        self.set_calls: list[tuple[UUID, UUID | None]] = []
        self.cleared: list[UUID] = []
        self.set_result = True  # False simulates a write that matched 0 docs
        self.create_folder_error: Exception | None = None

    async def get_conversation(self, conversation_id, workspace_id=None, owner_id=None):
        conv = self.conversations.get(conversation_id)
        if conv is not None and owner_id is not None and conv.owner_id != owner_id:
            return None
        return conv

    async def create_folder(self, folder):
        if self.create_folder_error is not None:
            raise self.create_folder_error
        self.folders[folder.folder_id] = folder
        return folder

    async def get_folder(self, workspace_id, owner_id, folder_id):
        return self.folders.get(folder_id)

    async def set_conversation_folder(self, conversation_id, folder_id, workspace_id, owner_id):
        self.set_calls.append((conversation_id, folder_id))
        if not self.set_result:
            return False
        conv = self.conversations.get(conversation_id)
        if conv:
            conv.folder_id = folder_id  # deliberately does NOT touch updated_at
        return True

    async def touch_folders(self, workspace_id, owner_id, folder_ids):
        self.touched.append(list(folder_ids))

    async def clear_folder(self, workspace_id, owner_id, folder_id):
        self.cleared.append(folder_id)
        n = 0
        for c in self.conversations.values():
            if c.folder_id == folder_id:
                c.folder_id = None
                n += 1
        return n

    async def delete_folder(self, workspace_id, owner_id, folder_id):
        return self.folders.pop(folder_id, None) is not None


@pytest.mark.asyncio
async def test_add_to_folder_bumps_destination_only_and_keeps_chat_date() -> None:
    ws, owner = uuid4(), uuid4()
    repo = _FakeRepo()
    conv = _conv(owner, ws)
    dest = _folder(owner, ws)
    repo.conversations[conv.conversation_id] = conv
    repo.folders[dest.folder_id] = dest

    result = await SetConversationFolderUseCase(repo).execute(
        conversation_id=conv.conversation_id,
        workspace_id=ws,
        owner_id=owner,
        folder_id=dest.folder_id,
    )

    assert isinstance(result, Success)
    assert result.unwrap().folder_id == dest.folder_id
    assert repo.touched == [[dest.folder_id]]
    assert conv.updated_at == _T0  # filing must not reorder Recent


@pytest.mark.asyncio
async def test_move_between_folders_bumps_both() -> None:
    ws, owner = uuid4(), uuid4()
    repo = _FakeRepo()
    src, dest = _folder(owner, ws), _folder(owner, ws)
    conv = _conv(owner, ws, folder_id=src.folder_id)
    repo.conversations[conv.conversation_id] = conv
    repo.folders[src.folder_id] = src
    repo.folders[dest.folder_id] = dest

    result = await SetConversationFolderUseCase(repo).execute(
        conversation_id=conv.conversation_id,
        workspace_id=ws,
        owner_id=owner,
        folder_id=dest.folder_id,
    )

    assert isinstance(result, Success)
    assert repo.touched == [[src.folder_id, dest.folder_id]]


@pytest.mark.asyncio
async def test_remove_from_folder_bumps_source() -> None:
    ws, owner = uuid4(), uuid4()
    repo = _FakeRepo()
    src = _folder(owner, ws)
    conv = _conv(owner, ws, folder_id=src.folder_id)
    repo.conversations[conv.conversation_id] = conv
    repo.folders[src.folder_id] = src

    result = await SetConversationFolderUseCase(repo).execute(
        conversation_id=conv.conversation_id,
        workspace_id=ws,
        owner_id=owner,
        folder_id=None,
    )

    assert isinstance(result, Success)
    assert result.unwrap().folder_id is None
    assert repo.touched == [[src.folder_id]]


@pytest.mark.asyncio
async def test_noop_when_already_in_folder() -> None:
    ws, owner = uuid4(), uuid4()
    repo = _FakeRepo()
    src = _folder(owner, ws)
    conv = _conv(owner, ws, folder_id=src.folder_id)
    repo.conversations[conv.conversation_id] = conv
    repo.folders[src.folder_id] = src

    result = await SetConversationFolderUseCase(repo).execute(
        conversation_id=conv.conversation_id,
        workspace_id=ws,
        owner_id=owner,
        folder_id=src.folder_id,
    )

    assert isinstance(result, Success)
    assert repo.set_calls == []  # no write
    assert repo.touched == []  # no date bump


@pytest.mark.asyncio
async def test_move_to_missing_folder_fails() -> None:
    ws, owner = uuid4(), uuid4()
    repo = _FakeRepo()
    conv = _conv(owner, ws)
    repo.conversations[conv.conversation_id] = conv

    result = await SetConversationFolderUseCase(repo).execute(
        conversation_id=conv.conversation_id,
        workspace_id=ws,
        owner_id=owner,
        folder_id=uuid4(),  # not in store
    )

    assert isinstance(result, Failure)
    assert repo.set_calls == []


@pytest.mark.asyncio
async def test_other_users_conversation_not_found() -> None:
    ws, owner = uuid4(), uuid4()
    repo = _FakeRepo()
    conv = _conv(uuid4(), ws)  # owned by someone else
    repo.conversations[conv.conversation_id] = conv

    result = await SetConversationFolderUseCase(repo).execute(
        conversation_id=conv.conversation_id,
        workspace_id=ws,
        owner_id=owner,
        folder_id=None,
    )

    assert isinstance(result, Failure)


@pytest.mark.asyncio
async def test_move_fails_when_conversation_vanishes_before_write() -> None:
    ws, owner = uuid4(), uuid4()
    repo = _FakeRepo()
    dest = _folder(owner, ws)
    conv = _conv(owner, ws)
    repo.conversations[conv.conversation_id] = conv
    repo.folders[dest.folder_id] = dest
    repo.set_result = False  # deleted between the read and the write

    result = await SetConversationFolderUseCase(repo).execute(
        conversation_id=conv.conversation_id,
        workspace_id=ws,
        owner_id=owner,
        folder_id=dest.folder_id,
    )

    assert isinstance(result, Failure)
    assert repo.touched == []  # no phantom date bump


@pytest.mark.asyncio
async def test_create_folder_duplicate_name_is_validation_error() -> None:
    repo = _FakeRepo()
    repo.create_folder_error = DuplicateKeyError("dup")

    result = await CreateFolderUseCase(repo).execute(
        workspace_id=uuid4(),
        owner_id=uuid4(),
        name="Research",
    )

    assert isinstance(result, Failure)
    assert result.failure().category == "validation"


@pytest.mark.asyncio
async def test_delete_folder_unfiles_chats_then_deletes() -> None:
    ws, owner = uuid4(), uuid4()
    repo = _FakeRepo()
    folder = _folder(owner, ws)
    conv = _conv(owner, ws, folder_id=folder.folder_id)
    repo.folders[folder.folder_id] = folder
    repo.conversations[conv.conversation_id] = conv

    result = await DeleteFolderUseCase(repo).execute(
        workspace_id=ws,
        owner_id=owner,
        folder_id=folder.folder_id,
    )

    assert isinstance(result, Success)
    assert repo.cleared == [folder.folder_id]  # unfiled before delete
    assert conv.folder_id is None
    assert folder.folder_id not in repo.folders


@pytest.mark.asyncio
async def test_delete_missing_folder_fails() -> None:
    repo = _FakeRepo()
    result = await DeleteFolderUseCase(repo).execute(
        workspace_id=uuid4(),
        owner_id=uuid4(),
        folder_id=uuid4(),
    )
    assert isinstance(result, Failure)
