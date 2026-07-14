"""Durable chat run routes: 409 on double send, resume replay/404, stop, active_run."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from returns.result import Success

from application.dtos.chat_dtos import AgentEvent
from application.use_cases.chat_use_cases import (
    DeleteConversationUseCase,
    GetConversationUseCase,
    SendMessageUseCase,
)
from application.use_cases.token_limit_use_cases import CheckTokenQuotaUseCase
from infrastructure.chat.run_registry import ChatRun, ChatRunRegistry
from interfaces.api.main import app
from interfaces.dependencies import get_auth, get_container
from tests.conftest import strip_authz_middleware
from tests.fakes.fake_auth import FakeAuth

WS = uuid4()
OWNER = uuid4()


class FakeQuota:
    async def execute(self, workspace_id, user_id):
        return Success(None)


class FakeSendUseCase:
    async def execute(self, **kwargs):
        yield AgentEvent(type="token", delta="hello")
        yield AgentEvent(type="done")


class FakeDeleteConversation:
    async def execute(self, **kwargs):
        return Success(None)


class FakeGetConversation:
    def __init__(self) -> None:
        from datetime import UTC, datetime

        from application.dtos.chat_dtos import ConversationDetailDTO

        now = datetime.now(UTC)
        self._make = lambda cid: ConversationDetailDTO(
            conversation_id=cid,
            workspace_id=WS,
            owner_id=OWNER,
            title="t",
            created_at=now,
            updated_at=now,
            message_count=0,
            messages=[],
        )

    async def execute(self, conversation_id, workspace_id, skip=0, limit=100):
        return self._make(conversation_id)


class FakeContainer:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]


def _client(registry: ChatRunRegistry) -> TestClient:
    strip_authz_middleware(app)
    app.dependency_overrides[get_container] = lambda: FakeContainer(
        {
            CheckTokenQuotaUseCase: FakeQuota(),
            SendMessageUseCase: FakeSendUseCase(),
            GetConversationUseCase: FakeGetConversation(),
            DeleteConversationUseCase: FakeDeleteConversation(),
            ChatRunRegistry: registry,
        },
    )
    app.dependency_overrides[get_auth] = lambda: FakeAuth(
        role="editor", user_id=OWNER, workspace_id=WS,
    )
    return TestClient(app)


def _seed_run(
    registry: ChatRunRegistry,
    cid: UUID,
    *,
    done: bool = False,
    frames: list[str] | None = None,
    workspace_id: UUID = WS,
    owner_id: UUID = OWNER,
) -> ChatRun:
    run = ChatRun(
        run_id=uuid4(),
        conversation_id=cid,
        workspace_id=workspace_id,
        owner_id=owner_id,
        done=done,
        events=frames or [],
    )
    registry._runs[cid] = run
    return run


def test_send_streams_seq_stamped_frames() -> None:
    registry = ChatRunRegistry()
    try:
        resp = _client(registry).post(f"/chat/{uuid4()}/messages", json={"message": "hi"})
        assert resp.status_code == 200
        assert "id: 0\nevent: token\n" in resp.text
        assert "id: 1\nevent: done\n" in resp.text
    finally:
        app.dependency_overrides.clear()


def test_send_conflicts_while_run_active() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    _seed_run(registry, cid, done=False)
    try:
        resp = _client(registry).post(f"/chat/{cid}/messages", json={"message": "hi"})
        assert resp.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_resume_replays_buffered_frames() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    frames = ["id: 0\nevent: token\ndata: {}\n\n", "id: 1\nevent: done\ndata: {}\n\n"]
    _seed_run(registry, cid, done=True, frames=frames)
    try:
        resp = _client(registry).get(f"/chat/{cid}/messages/stream")
        assert resp.status_code == 200
        assert resp.text == "".join(frames)
    finally:
        app.dependency_overrides.clear()


def test_resume_honors_after_offset() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    frames = ["id: 0\nevent: token\ndata: {}\n\n", "id: 1\nevent: done\ndata: {}\n\n"]
    _seed_run(registry, cid, done=True, frames=frames)
    try:
        resp = _client(registry).get(f"/chat/{cid}/messages/stream?after=0")
        assert resp.text == frames[1]
    finally:
        app.dependency_overrides.clear()


def test_resume_404_when_no_run() -> None:
    registry = ChatRunRegistry()
    try:
        resp = _client(registry).get(f"/chat/{uuid4()}/messages/stream")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_resume_404_for_other_users_run() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    _seed_run(registry, cid, done=True, owner_id=uuid4())  # someone else's run
    try:
        resp = _client(registry).get(f"/chat/{cid}/messages/stream")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_stop_cancels_active_run() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    _seed_run(registry, cid, done=False)
    try:
        resp = _client(registry).delete(f"/chat/{cid}/run")
        assert resp.status_code == 204
        assert registry.active(cid) is None
    finally:
        app.dependency_overrides.clear()


def test_stop_404_when_no_run() -> None:
    registry = ChatRunRegistry()
    try:
        resp = _client(registry).delete(f"/chat/{uuid4()}/run")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_stop_404_for_other_users_run() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    _seed_run(registry, cid, done=False, owner_id=uuid4())
    try:
        resp = _client(registry).delete(f"/chat/{cid}/run")
        assert resp.status_code == 404
        assert registry.active(cid) is not None  # untouched
    finally:
        app.dependency_overrides.clear()


def test_conversation_detail_reports_active_run() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    _seed_run(registry, cid, done=False)
    try:
        resp = _client(registry).get(f"/chat/{cid}")
        assert resp.status_code == 200
        assert resp.json()["active_run"] is True
    finally:
        app.dependency_overrides.clear()


def test_conversation_detail_active_run_false_when_done() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    _seed_run(registry, cid, done=True)  # finished, inside eviction grace
    try:
        resp = _client(registry).get(f"/chat/{cid}")
        assert resp.json()["active_run"] is False
    finally:
        app.dependency_overrides.clear()


def test_delete_conversation_stops_active_run() -> None:
    registry = ChatRunRegistry()
    cid = uuid4()
    _seed_run(registry, cid, done=False)
    try:
        resp = _client(registry).delete(f"/chat/{cid}")
        assert resp.status_code == 204
        assert registry.active(cid) is None
    finally:
        app.dependency_overrides.clear()
