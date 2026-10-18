"""GET/PUT /workspace/chat-settings — a workspace admin switches answer formatting."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from application.ports.workspace_chat_settings import WorkspaceChatSettingsStore
from infrastructure.config import Settings
from interfaces.api.main import app
from interfaces.dependencies import get_auth, get_container
from tests.conftest import strip_authz_middleware
from tests.fakes.fake_auth import FakeAuth


class Store:
    def __init__(self) -> None:
        self.on: bool | None = None

    async def get_answer_formatting(self, workspace_id):
        return self.on

    async def set_answer_formatting(self, workspace_id, on, *, updated_by):
        self.on = on


class FakeContainer(dict):
    pass


def _client(*, role="admin", server_default=True):
    store = Store()
    container = FakeContainer({
        Settings: SimpleNamespace(chat_enable_answer_formatting=server_default),
        WorkspaceChatSettingsStore: store,
    })
    strip_authz_middleware(app)
    app.dependency_overrides[get_container] = lambda: container
    app.dependency_overrides[get_auth] = lambda: FakeAuth(role=role, user_id=uuid4(), workspace_id=uuid4())
    return TestClient(app), store


def test_unset_follows_the_server_default() -> None:
    try:
        for default in (True, False):
            client, _ = _client(role="editor", server_default=default)
            assert client.get("/workspace/chat-settings").json() == {
                "answer_formatting": default,
                "can_manage": False,
            }
    finally:
        app.dependency_overrides.clear()


def test_only_an_admin_can_switch_it_and_it_sticks() -> None:
    try:
        client, store = _client(role="editor")
        resp = client.put("/workspace/chat-settings", json={"answer_formatting": False})
        assert resp.status_code == 403
        assert store.on is None

        client, store = _client(role="admin")
        assert client.put("/workspace/chat-settings", json={"answer_formatting": False}).status_code == 204
        assert store.on is False
        assert client.get("/workspace/chat-settings").json() == {
            "answer_formatting": False,
            "can_manage": True,
        }
    finally:
        app.dependency_overrides.clear()
