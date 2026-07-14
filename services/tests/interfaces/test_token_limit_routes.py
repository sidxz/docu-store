"""Admin CRUD for workspace token limits."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from application.dtos.usage_dtos import TokenLimitEntry
from application.ports.token_limit_store import TokenLimitStore
from interfaces.api.main import app
from interfaces.dependencies import get_auth, get_container
from tests.conftest import strip_authz_middleware
from tests.fakes.fake_auth import FakeAuth

USER_A = uuid4()
ADMIN_ID = uuid4()
WS_ID = uuid4()


class FakeLimitStore:
    def __init__(self) -> None:
        self.rows = [
            TokenLimitEntry(user_id=None, limit=1_000_000),
            TokenLimitEntry(user_id=USER_A, limit=None),
        ]
        self.set_calls: list[tuple] = []
        self.delete_calls: list[tuple] = []

    async def list_for_workspace(self, workspace_id):
        return self.rows

    async def set(self, workspace_id, user_id, limit, updated_by):
        self.set_calls.append((workspace_id, user_id, limit, updated_by))

    async def delete(self, workspace_id, user_id):
        self.delete_calls.append((workspace_id, user_id))


class FakeContainer:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]


def _client(store: FakeLimitStore, *, is_admin: bool = True) -> TestClient:
    strip_authz_middleware(app)
    app.dependency_overrides[get_container] = lambda: FakeContainer({TokenLimitStore: store})
    app.dependency_overrides[get_auth] = lambda: FakeAuth(
        role="admin" if is_admin else "viewer", user_id=ADMIN_ID, workspace_id=WS_ID,
    )
    return TestClient(app)


def test_get_limits_requires_admin() -> None:
    try:
        assert _client(FakeLimitStore(), is_admin=False).get("/workspace/token-limits").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_get_limits_splits_default_and_overrides() -> None:
    try:
        resp = _client(FakeLimitStore()).get("/workspace/token-limits")
        assert resp.status_code == 200
        body = resp.json()
        assert body["default_limit"] == 1_000_000
        assert body["overrides"] == [{"user_id": str(USER_A), "limit": None}]
    finally:
        app.dependency_overrides.clear()


def test_put_default_upserts_null_user_row() -> None:
    store = FakeLimitStore()
    try:
        resp = _client(store).put("/workspace/token-limits/default", json={"limit": 5_000_000})
        assert resp.status_code == 204
        assert store.set_calls == [(WS_ID, None, 5_000_000, ADMIN_ID)]
    finally:
        app.dependency_overrides.clear()


def test_put_user_override_and_delete() -> None:
    store = FakeLimitStore()
    try:
        client = _client(store)
        assert client.put(f"/workspace/token-limits/{USER_A}", json={"limit": None}).status_code == 204
        assert store.set_calls == [(WS_ID, USER_A, None, ADMIN_ID)]
        assert client.delete(f"/workspace/token-limits/{USER_A}").status_code == 204
        assert store.delete_calls == [(WS_ID, USER_A)]
    finally:
        app.dependency_overrides.clear()


def test_put_rejects_negative_limit() -> None:
    try:
        resp = _client(FakeLimitStore()).put("/workspace/token-limits/default", json={"limit": -1})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_put_rejects_missing_limit_field() -> None:
    """{} must 422, not silently mean unlimited — explicit null is the only unlimited."""
    try:
        client = _client(FakeLimitStore())
        assert client.put("/workspace/token-limits/default", json={}).status_code == 422
        assert client.put(f"/workspace/token-limits/{USER_A}", json={}).status_code == 422
        assert client.put(
            "/workspace/token-limits/default", json={"limit": None},
        ).status_code == 204
    finally:
        app.dependency_overrides.clear()


def test_put_rejects_limit_beyond_int64() -> None:
    """Values past Mongo's 8-byte int ceiling must 422, not 500 in BSON encoding."""
    try:
        resp = _client(FakeLimitStore()).put(
            "/workspace/token-limits/default", json={"limit": 2**63},
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_mutations_require_admin() -> None:
    try:
        client = _client(FakeLimitStore(), is_admin=False)
        assert client.put("/workspace/token-limits/default", json={"limit": 1}).status_code == 403
        assert client.put(f"/workspace/token-limits/{USER_A}", json={"limit": 1}).status_code == 403
        assert client.delete(f"/workspace/token-limits/{USER_A}").status_code == 403
    finally:
        app.dependency_overrides.clear()
