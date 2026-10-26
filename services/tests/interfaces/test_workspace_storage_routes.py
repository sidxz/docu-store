"""Admin storage summary and limit: GET /workspace/storage, PUT /workspace/storage/limit."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from application.dtos.usage_dtos import WorkspaceStorage
from application.ports.workspace_storage_limit_store import WorkspaceStorageLimitStore
from application.use_cases.storage_limit_use_cases import MIB, GetWorkspaceStorageUseCase
from infrastructure.config import Settings
from interfaces.api.main import app
from interfaces.dependencies import get_auth, get_container
from tests.conftest import strip_authz_middleware
from tests.fakes.fake_auth import FakeAuth

ADMIN_ID = uuid4()
WS = uuid4()
SUMMARY = WorkspaceStorage(
    uploaded_bytes=10 * MIB,
    on_disk_bytes=80 * MIB,
    limit_bytes=None,
    cap_bytes=100 * MIB,
    effective_limit_bytes=100 * MIB,
)


class FakeGetStorage:
    async def execute(self, workspace_id):
        assert workspace_id == WS
        return SUMMARY


class FakeLimitStore:
    def __init__(self) -> None:
        self.set_calls: list[tuple] = []

    async def set_limit(self, workspace_id, limit_bytes, *, updated_by):
        self.set_calls.append((workspace_id, limit_bytes, updated_by))


class FakeContainer:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]


def _client(store: FakeLimitStore, *, is_admin: bool = True, cap_mb: int | None = None):
    strip_authz_middleware(app)
    app.dependency_overrides[get_container] = lambda: FakeContainer(
        {
            GetWorkspaceStorageUseCase: FakeGetStorage(),
            WorkspaceStorageLimitStore: store,
            Settings: SimpleNamespace(max_workspace_storage_mb=cap_mb),
        }
    )
    app.dependency_overrides[get_auth] = lambda: FakeAuth(
        role="admin" if is_admin else "viewer", user_id=ADMIN_ID, workspace_id=WS
    )
    return TestClient(app)


def _put(store, body, **kwargs):
    try:
        return _client(store, **kwargs).put("/workspace/storage/limit", json=body)
    finally:
        app.dependency_overrides.clear()


def test_get_storage_requires_admin() -> None:
    try:
        resp = _client(FakeLimitStore(), is_admin=False).get("/workspace/storage")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_get_storage_returns_summary() -> None:
    try:
        resp = _client(FakeLimitStore()).get("/workspace/storage")
        assert resp.status_code == 200
        assert resp.json() == {
            "uploaded_bytes": 10 * MIB,
            "on_disk_bytes": 80 * MIB,
            "limit_bytes": None,
            "cap_bytes": 100 * MIB,
            "effective_limit_bytes": 100 * MIB,
        }
    finally:
        app.dependency_overrides.clear()


def test_put_limit_saves_bytes() -> None:
    store = FakeLimitStore()
    resp = _put(store, {"limit_bytes": 5 * MIB})
    assert resp.status_code == 204
    assert store.set_calls == [(WS, 5 * MIB, ADMIN_ID)]


def test_put_limit_null_clears() -> None:
    store = FakeLimitStore()
    resp = _put(store, {"limit_bytes": None})
    assert resp.status_code == 204
    assert store.set_calls == [(WS, None, ADMIN_ID)]


def test_put_limit_zero_is_saved_not_unlimited() -> None:
    store = FakeLimitStore()
    resp = _put(store, {"limit_bytes": 0})
    assert resp.status_code == 204
    assert store.set_calls == [(WS, 0, ADMIN_ID)]


def test_put_limit_above_cap_is_422() -> None:
    store = FakeLimitStore()
    resp = _put(store, {"limit_bytes": 200 * MIB}, cap_mb=100)
    assert resp.status_code == 422
    assert resp.json()["detail"] == "The limit can't be above this deployment's cap of 100 MB."
    assert store.set_calls == []


def test_put_limit_requires_the_field() -> None:
    store = FakeLimitStore()
    assert _put(store, {}).status_code == 422
    assert store.set_calls == []


def test_put_limit_requires_admin() -> None:
    store = FakeLimitStore()
    assert _put(store, {"limit_bytes": 1}, is_admin=False).status_code == 403
    assert store.set_calls == []
