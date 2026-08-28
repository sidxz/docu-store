"""/user/llm-provider — a registry of providers with one active, not a single slot."""

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
from infrastructure.llm import openrouter_catalog
from infrastructure.llm.provider_probe import NerProbe
from interfaces.api.main import app
from interfaces.api.routes import user_routes
from interfaces.dependencies import get_auth, get_container
from tests.conftest import strip_authz_middleware
from tests.fakes.fake_auth import FakeAuth

KEY = "not-a-real-key-abcdef1234"
OAI_KEY = "not-a-real-openai-key-5678"


def _entry(provider: str, model: str, chat: str, last4: str, *, active: bool) -> UserLLMProviderEntry:
    return UserLLMProviderEntry(
        provider=provider, model=model, chat_model=chat, key_last4=last4, active=active
    )


ROUTER = _entry("openrouter", "openai/gpt-5-mini", "openai/gpt-5", "1234", active=True)
OPENAI = _entry("openai", "gpt-5.6-luna", "gpt-5.6-luna", "5678", active=False)
ROUTER_CFG = UserLLMConfig(
    provider="openai",
    api_key=KEY,
    base_url="https://openrouter.ai/api/v1",
    model="openai/gpt-5-mini",
    chat_model="openai/gpt-5",
)
OPENAI_CFG = UserLLMConfig(
    provider="openai", api_key=OAI_KEY, model="gpt-5.6-luna", chat_model="gpt-5.6-luna"
)


class FakeStore:
    """Entries keyed by provider; ``active`` lives on the entry, as in Mongo."""

    def __init__(self, *entries: UserLLMProviderEntry, configs: dict | None = None) -> None:
        self.entries = list(entries)
        self.configs = configs or {}
        self.set_calls: list[dict] = []
        self.update_calls: list[dict] = []
        self.activated: list[str] = []
        self.deleted: list[str] = []

    def _active(self) -> UserLLMProviderEntry | None:
        return next((e for e in self.entries if e.active), None)

    async def get(self, workspace_id, user_id):
        active = self._active()
        return self.configs.get(active.provider) if active else None

    async def get_config(self, workspace_id, user_id, provider):
        return self.configs.get(provider)

    async def get_entry(self, workspace_id, user_id):
        return self._active()

    async def list_entries(self, workspace_id, user_id):
        return list(self.entries)

    async def set(self, workspace_id, user_id, **kw):
        self.set_calls.append(kw)

    async def update_models(self, workspace_id, user_id, **kw):
        self.update_calls.append(kw)
        return any(e.provider == kw["provider"] for e in self.entries)

    async def activate(self, workspace_id, user_id, provider):
        self.activated.append(provider)
        return True

    async def delete(self, workspace_id, user_id, provider):
        self.deleted.append(provider)
        return True


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


@pytest.fixture(autouse=True)
def _ner_ok(monkeypatch: pytest.MonkeyPatch):
    """A usable config by default; no route test may reach a provider."""
    _stub_ner(monkeypatch, NerProbe(ok=True))


def _stub_ner(monkeypatch: pytest.MonkeyPatch, probe: NerProbe) -> list[UserLLMConfig]:
    seen: list[UserLLMConfig] = []

    async def fake(cfg, *, allow_cloud):
        seen.append(cfg)
        return probe

    monkeypatch.setattr(user_routes, "probe_ner_support", fake)
    return seen


@pytest.fixture(autouse=True)
def _offline_catalog(monkeypatch: pytest.MonkeyPatch):
    """No route test reaches OpenRouter; GET reads the catalog for its suggestions."""

    async def fake():
        return {
            "openai/gpt-5.6-luna": frozenset({"structured_outputs", "tools"}),
            "google/gemini-3.7-flash": frozenset({"structured_outputs", "tools"}),
        }

    monkeypatch.setattr(openrouter_catalog, "_fetch_catalog", fake)
    monkeypatch.setattr(openrouter_catalog, "_cache", None)
    monkeypatch.setattr(openrouter_catalog, "_cached_at", 0.0)


# ── GET: the whole registry, never a key ──


def test_get_flag_off_reports_disabled_with_presets() -> None:
    resp = _client(FakeStore(), enabled=False).get("/user/llm-provider")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False and body["configured"] is False
    assert body["providers"] == []
    assert set(body["presets"]) == {"openrouter", "openai", "gemini"}
    assert body["presets"]["openai"] == {"model": "gpt-5-mini", "chat_model": "gpt-5"}


def test_get_suggests_models_for_the_two_direct_providers_only() -> None:
    """OpenRouter's own users pick their own model; the field is free text regardless."""
    body = _client(FakeStore(), enabled=False).get("/user/llm-provider").json()

    assert body["suggestions"] == {
        "openrouter": [],
        "openai": ["gpt-5.6-luna"],
        "gemini": ["gemini-3.7-flash"],
    }


def test_get_lists_every_provider_and_marks_the_active_one() -> None:
    store = FakeStore(ROUTER, OPENAI, configs={"openrouter": ROUTER_CFG, "openai": OPENAI_CFG})
    resp = _client(store).get("/user/llm-provider")
    body = resp.json()

    assert body["configured"] is True
    assert [(p["provider"], p["active"]) for p in body["providers"]] == [
        ("openrouter", True),
        ("openai", False),
    ]
    assert body["providers"][1]["key_last4"] == "5678"
    assert KEY not in resp.text and OAI_KEY not in resp.text


def test_configured_is_false_when_nothing_is_active() -> None:
    """Deleting the active provider leaves the others stored but nothing running."""
    inactive = _entry("openai", "gpt-5.6-luna", "gpt-5.6-luna", "5678", active=False)

    body = _client(FakeStore(inactive)).get("/user/llm-provider").json()

    assert body["configured"] is False
    assert len(body["providers"]) == 1


# ── PUT: additive. Adding a provider never touches another provider's key ──


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


def test_adding_a_second_provider_leaves_the_first_alone() -> None:
    """The bug this registry exists for: connecting OpenRouter used to erase the OpenAI key."""
    store = FakeStore(OPENAI, configs={"openai": OPENAI_CFG})

    resp = _client(store).put("/user/llm-provider", json={"provider": "openrouter", "api_key": KEY})

    assert resp.status_code == 204
    assert store.set_calls[0]["provider"] == "openrouter"
    assert [e.provider for e in store.entries] == ["openai"]  # untouched by the route


def test_put_without_key_updates_that_providers_models_only() -> None:
    store = FakeStore(ROUTER, OPENAI, configs={"openrouter": ROUTER_CFG, "openai": OPENAI_CFG})
    resp = _client(store).put(
        "/user/llm-provider", json={"provider": "openai", "model": "x", "chat_model": "y"}
    )
    assert resp.status_code == 204
    assert store.update_calls == [{"provider": "openai", "model": "x", "chat_model": "y"}]
    assert store.set_calls == []


def test_put_without_key_fills_blanks_from_the_named_providers_preset() -> None:
    store = FakeStore(OPENAI, configs={"openai": OPENAI_CFG})
    resp = _client(store).put("/user/llm-provider", json={"provider": "openai", "model": ""})
    assert resp.status_code == 204
    assert store.update_calls == [
        {"provider": "openai", "model": "gpt-5-mini", "chat_model": "gpt-5"}
    ]


def test_put_without_key_and_without_that_provider_is_404() -> None:
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
    assert c.delete("/user/llm-provider/openai").status_code == 404
    assert c.post("/user/llm-provider/openai/test").status_code == 404
    assert c.post("/user/llm-provider/openai/activate").status_code == 404


# ── Activate / delete / test, each addressing one provider ──


def test_activate_switches_which_provider_runs() -> None:
    store = FakeStore(ROUTER, OPENAI, configs={"openrouter": ROUTER_CFG, "openai": OPENAI_CFG})

    assert _client(store).post("/user/llm-provider/openai/activate").status_code == 204
    assert store.activated == ["openai"]


def test_activate_refuses_a_provider_that_cannot_run_entity_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_ner(monkeypatch, NerProbe(ok=False, detail="json_schema unsupported", refused=True))
    store = FakeStore(ROUTER, OPENAI, configs={"openrouter": ROUTER_CFG, "openai": OPENAI_CFG})

    resp = _client(store).post("/user/llm-provider/openai/activate")

    assert resp.status_code == 422
    assert "entity extraction" in resp.json()["detail"]
    assert store.activated == []


def test_activate_404s_for_a_provider_with_no_stored_key() -> None:
    store = FakeStore(ROUTER, configs={"openrouter": ROUTER_CFG})
    assert _client(store).post("/user/llm-provider/gemini/activate").status_code == 404
    assert _client(store).post("/user/llm-provider/azure/activate").status_code == 404


def test_delete_removes_only_the_named_provider() -> None:
    store = FakeStore(ROUTER, OPENAI, configs={"openrouter": ROUTER_CFG, "openai": OPENAI_CFG})
    assert _client(store).delete("/user/llm-provider/openrouter").status_code == 204
    assert store.deleted == ["openrouter"]


def test_test_endpoint_404_without_that_provider() -> None:
    assert _client(FakeStore()).post("/user/llm-provider/openai/test").status_code == 404


def test_an_inactive_provider_can_be_tested_before_switching_to_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point: find out it does not work while the working one still runs."""
    seen: dict = {}

    async def fake_probe(cfg, *, allow_cloud):
        seen["cfg"], seen["allow_cloud"] = cfg, allow_cloud
        return {"batch": (True, None), "chat": (False, "The provider rejected the key (401).")}

    monkeypatch.setattr(user_routes, "probe_user_llm_config", fake_probe)
    store = FakeStore(ROUTER, OPENAI, configs={"openrouter": ROUTER_CFG, "openai": OPENAI_CFG})

    resp = _client(store).post("/user/llm-provider/openai/test")

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "lanes": {
            "batch": {"ok": True, "detail": None},
            "chat": {"ok": False, "detail": "The provider rejected the key (401)."},
        },
    }
    assert seen["cfg"] is OPENAI_CFG  # the one asked for, not the active one
    assert seen["allow_cloud"] is True
    assert OAI_KEY not in resp.text


def test_test_probes_the_models_in_the_request_not_the_stored_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """You test a model to find out whether it works — needing to save it first
    would mean committing to it to learn it was wrong."""
    seen: dict = {}

    async def fake_probe(cfg, *, allow_cloud):
        seen["cfg"] = cfg
        return {"batch": (True, None)}

    monkeypatch.setattr(user_routes, "probe_user_llm_config", fake_probe)
    store = FakeStore(ROUTER, configs={"openrouter": ROUTER_CFG})

    resp = _client(store).post(
        "/user/llm-provider/openrouter/test",
        json={"model": "typed/but-not-saved", "chat_model": "typed/chat"},
    )

    assert resp.status_code == 200
    assert seen["cfg"].model == "typed/but-not-saved"
    assert seen["cfg"].chat_model == "typed/chat"
    assert seen["cfg"].api_key == KEY  # the stored key, never one from the request


def test_blank_overrides_resolve_the_way_a_save_would(monkeypatch: pytest.MonkeyPatch) -> None:
    """So a green test is a statement about the save that would follow it."""
    seen: dict = {}

    async def fake_probe(cfg, *, allow_cloud):
        seen["cfg"] = cfg
        return {"batch": (True, None)}

    monkeypatch.setattr(user_routes, "probe_user_llm_config", fake_probe)
    store = FakeStore(ROUTER, configs={"openrouter": ROUTER_CFG})

    _client(store).post("/user/llm-provider/openrouter/test", json={"model": "", "chat_model": ""})

    assert seen["cfg"].model == "openai/gpt-5-mini"  # the openrouter preset
    assert seen["cfg"].chat_model == "openai/gpt-5"


# ── The capability gate lands on what runs, not on what is merely stored ──


def test_put_with_a_key_is_gated_because_it_activates(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_ner(monkeypatch, NerProbe(ok=False, detail="json_schema unsupported", refused=True))
    store = FakeStore()
    resp = _client(store).put("/user/llm-provider", json={"provider": "openrouter", "api_key": KEY})

    assert resp.status_code == 422
    assert store.set_calls == []  # nothing reached storage


def test_put_still_saves_when_the_probe_only_failed_transiently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider outage must not stop someone configuring their way out of it."""
    _stub_ner(monkeypatch, NerProbe(ok=False, detail="rate limited", refused=False))
    store = FakeStore()
    resp = _client(store).put("/user/llm-provider", json={"provider": "openrouter", "api_key": KEY})

    assert resp.status_code == 204
    assert len(store.set_calls) == 1


def test_put_probes_the_config_it_is_about_to_write(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _stub_ner(monkeypatch, NerProbe(ok=True))
    _client(FakeStore()).put(
        "/user/llm-provider",
        json={"provider": "openrouter", "api_key": KEY, "model": "some/model"},
    )

    assert len(seen) == 1
    # openrouter resolves to openai + its base URL before the probe, exactly as the
    # NER adapter will see it at ingestion time.
    assert seen[0].provider == "openai"
    assert seen[0].base_url == "https://openrouter.ai/api/v1"
    assert seen[0].model == "some/model"


def test_a_model_change_on_the_active_provider_is_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _stub_ner(monkeypatch, NerProbe(ok=False, detail="no", refused=True))
    store = FakeStore(ROUTER, configs={"openrouter": ROUTER_CFG})

    resp = _client(store).put(
        "/user/llm-provider", json={"provider": "openrouter", "model": "worse/model"},
    )

    assert resp.status_code == 422
    assert seen[0].model == "worse/model"
    assert store.update_calls == []


def test_a_model_change_on_an_inactive_provider_is_not_gated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Editing a provider that is not running costs nothing; activating it is the gate."""
    seen = _stub_ner(monkeypatch, NerProbe(ok=False, detail="no", refused=True))
    store = FakeStore(ROUTER, OPENAI, configs={"openrouter": ROUTER_CFG, "openai": OPENAI_CFG})

    resp = _client(store).put(
        "/user/llm-provider", json={"provider": "openai", "model": "anything"},
    )

    assert resp.status_code == 204
    assert seen == []
    assert store.update_calls == [
        {"provider": "openai", "model": "anything", "chat_model": "gpt-5"}
    ]
