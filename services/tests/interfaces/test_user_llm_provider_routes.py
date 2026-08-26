"""GET/PUT/DELETE /user/llm-provider + POST /user/llm-provider/test."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from application.ports.user_llm_config import (
    UserLLMConfig,
    UserLLMConfigStore,
    UserLLMProviderEntry,
)
from infrastructure.config import Settings
from interfaces.api.main import app
from interfaces.api.routes import user_routes
from interfaces.dependencies import get_auth, get_container
from tests.conftest import strip_authz_middleware
from tests.fakes.fake_auth import FakeAuth

KEY = "not-a-real-key-abcdef1234"
ENTRY = UserLLMProviderEntry(provider="openrouter", model="openai/gpt-5-mini", chat_model="openai/gpt-5", key_last4="1234")
CFG = UserLLMConfig(provider="openai", api_key=KEY, base_url="https://openrouter.ai/api/v1", model="openai/gpt-5-mini", chat_model="openai/gpt-5")


class FakeStore:
    def __init__(self, entry=None, config=None) -> None:
        self.entry, self.config = entry, config
        self.set_calls: list[dict] = []
        self.update_calls: list[dict] = []
        self.delete_calls = 0

    async def get(self, workspace_id, user_id):
        return self.config

    async def get_entry(self, workspace_id, user_id):
        return self.entry

    async def set(self, workspace_id, user_id, **kw):
        self.set_calls.append(kw)

    async def update_models(self, workspace_id, user_id, **kw):
        self.update_calls.append(kw)
        return self.entry is not None

    async def delete(self, workspace_id, user_id):
        self.delete_calls += 1


class FakeContainer:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]


def _client(store: FakeStore, *, enabled: bool = True) -> TestClient:
    strip_authz_middleware(app)
    app.dependency_overrides[get_container] = lambda: FakeContainer(
        {
            Settings: SimpleNamespace(user_llm_keys_enabled=enabled, allow_cloud_llm=True),
            UserLLMConfigStore: store,
        },
    )
    app.dependency_overrides[get_auth] = lambda: FakeAuth(role="viewer", user_id=uuid4(), workspace_id=uuid4())
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_get_flag_off_reports_disabled_with_presets() -> None:
    resp = _client(FakeStore(), enabled=False).get("/user/llm-provider")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False and body["configured"] is False
    assert set(body["presets"]) == {"openrouter", "openai", "gemini"}
    assert body["presets"]["openai"] == {"model": "gpt-5-mini", "chat_model": "gpt-5"}


def test_get_configured_never_includes_the_key() -> None:
    resp = _client(FakeStore(entry=ENTRY, config=CFG)).get("/user/llm-provider")
    body = resp.json()
    assert body["configured"] is True
    assert body["provider"] == "openrouter" and body["key_last4"] == "1234"
    assert body["model"] == "openai/gpt-5-mini" and body["chat_model"] == "openai/gpt-5"
    assert KEY not in resp.text


def test_put_fills_blank_models_from_preset_and_strips() -> None:
    store = FakeStore()
    resp = _client(store).put(
        "/user/llm-provider",
        json={"provider": "gemini", "api_key": f"  {KEY}  ", "model": "  ", "chat_model": "gemini-2.5-pro"},
    )
    assert resp.status_code == 204
    assert store.set_calls == [
        {"provider": "gemini", "api_key": KEY, "model": "gemini-2.5-flash", "chat_model": "gemini-2.5-pro"},
    ]


def test_put_without_key_updates_models_only() -> None:
    store = FakeStore(entry=ENTRY)
    resp = _client(store).put("/user/llm-provider", json={"provider": "openrouter", "model": "x", "chat_model": "y"})
    assert resp.status_code == 204
    assert store.update_calls == [{"model": "x", "chat_model": "y"}]
    assert store.set_calls == []


def test_put_without_key_fills_blanks_from_stored_provider_not_body_provider() -> None:
    # Body names "gemini" (just picking the models UI is on), but the stored
    # entry is "openrouter" — the blank-fill must use the STORED preset.
    store = FakeStore(entry=ENTRY)
    resp = _client(store).put("/user/llm-provider", json={"provider": "gemini", "model": ""})
    assert resp.status_code == 204
    assert store.update_calls == [{"model": "openai/gpt-5-mini", "chat_model": "openai/gpt-5"}]


def test_put_without_key_and_without_row_is_404() -> None:
    resp = _client(FakeStore()).put("/user/llm-provider", json={"provider": "openrouter", "model": "x"})
    assert resp.status_code == 404


def test_put_rejects_unknown_provider_and_short_key() -> None:
    assert _client(FakeStore()).put("/user/llm-provider", json={"provider": "azure", "api_key": KEY}).status_code == 422
    resp = _client(FakeStore()).put("/user/llm-provider", json={"provider": "openai", "api_key": "abc1234"})
    assert resp.status_code == 422
    assert "abc1234" not in resp.text


def test_writes_are_404_when_flag_off() -> None:
    c = _client(FakeStore(), enabled=False)
    assert c.put("/user/llm-provider", json={"provider": "openai", "api_key": KEY}).status_code == 404
    assert c.delete("/user/llm-provider").status_code == 404
    assert c.post("/user/llm-provider/test").status_code == 404


def test_delete_removes_row() -> None:
    store = FakeStore(entry=ENTRY)
    assert _client(store).delete("/user/llm-provider").status_code == 204
    assert store.delete_calls == 1


def test_test_endpoint_404_without_config() -> None:
    assert _client(FakeStore()).post("/user/llm-provider/test").status_code == 404


def test_test_endpoint_maps_lane_results(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    async def fake_probe(cfg, *, allow_cloud):
        seen["cfg"], seen["allow_cloud"] = cfg, allow_cloud
        return {"batch": (True, None), "chat": (False, "The provider rejected the key (401).")}

    monkeypatch.setattr(user_routes, "probe_user_llm_config", fake_probe)
    resp = _client(FakeStore(entry=ENTRY, config=CFG)).post("/user/llm-provider/test")
    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "lanes": {
            "batch": {"ok": True, "detail": None},
            "chat": {"ok": False, "detail": "The provider rejected the key (401)."},
        },
    }
    assert seen["cfg"] is CFG and seen["allow_cloud"] is True
    assert KEY not in resp.text
