"""Pure-logic tests for MongoUserLLMProviderStore (fake collection, no DB)."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pymongo.errors import DuplicateKeyError

from application.ports.user_llm_config import UserLLMProviderEntry
from application.services.llm_providers import OPENROUTER_BASE_URL
from infrastructure.read_repositories.mongo_user_llm_provider_store import (
    MongoUserLLMProviderStore,
    _doc_to_entry,
    _entry_doc,
    user_llm_fernet,
)

KEY = "not-a-real-key-abcdef1234"


class _FakeColl:
    def __init__(self) -> None:
        self.docs: dict[tuple[str, str], dict] = {}
        self.indexes: list = []

    @staticmethod
    def _k(q: dict) -> tuple[str, str]:
        return (q["workspace_id"], q["user_id"])

    async def find_one(self, q: dict) -> dict | None:
        return self.docs.get(self._k(q))

    async def replace_one(self, q: dict, doc: dict, upsert: bool = False) -> None:
        self.docs[self._k(q)] = doc

    async def update_one(self, q: dict, update: dict):
        doc = self.docs.get(self._k(q))
        if doc is not None:
            doc.update(update["$set"])
        return type("R", (), {"matched_count": 0 if doc is None else 1})()

    async def delete_one(self, q: dict) -> None:
        self.docs.pop(self._k(q), None)

    async def create_index(self, keys, **kw) -> None:
        self.indexes.append((keys, kw))


def _store(coll: _FakeColl | None = None) -> tuple[MongoUserLLMProviderStore, _FakeColl]:
    coll = coll or _FakeColl()
    store = object.__new__(MongoUserLLMProviderStore)
    store._coll = coll
    store._fernet = Fernet(Fernet.generate_key())
    return store, coll


async def test_set_then_get_entry_exposes_only_last4() -> None:
    store, coll = _store()
    ws, user = uuid4(), uuid4()
    await store.set(ws, user, provider="openrouter", api_key=KEY, model="m", chat_model="c")
    entry = await store.get_entry(ws, user)
    assert entry == UserLLMProviderEntry(provider="openrouter", model="m", chat_model="c", key_last4="1234")
    # The raw key never lands in the document.
    assert KEY not in json.dumps(next(iter(coll.docs.values())), default=str)


async def test_get_decrypts_and_maps_openrouter_to_openai_plus_base_url() -> None:
    store, _ = _store()
    ws, user = uuid4(), uuid4()
    await store.set(ws, user, provider="openrouter", api_key=KEY, model="m", chat_model="c")
    cfg = await store.get(ws, user)
    assert cfg is not None
    assert cfg.provider == "openai"
    assert cfg.base_url == OPENROUTER_BASE_URL
    assert cfg.api_key == KEY
    assert (cfg.model, cfg.chat_model) == ("m", "c")
    assert KEY not in repr(cfg)  # repr=False on api_key (Phase 2)


async def test_get_for_direct_provider_has_no_base_url() -> None:
    store, _ = _store()
    ws, user = uuid4(), uuid4()
    await store.set(ws, user, provider="gemini", api_key=KEY, model="m", chat_model="c")
    cfg = await store.get(ws, user)
    assert cfg is not None and cfg.provider == "gemini" and cfg.base_url is None


async def test_missing_row_is_none_everywhere() -> None:
    store, _ = _store()
    assert await store.get(uuid4(), uuid4()) is None
    assert await store.get_entry(uuid4(), uuid4()) is None


async def test_update_models_keeps_key_and_reports_missing_row() -> None:
    store, _ = _store()
    ws, user = uuid4(), uuid4()
    assert await store.update_models(ws, user, model="x", chat_model="y") is False
    await store.set(ws, user, provider="openai", api_key=KEY, model="m", chat_model="c")
    assert await store.update_models(ws, user, model="x", chat_model="y") is True
    entry = await store.get_entry(ws, user)
    assert (entry.model, entry.chat_model, entry.key_last4) == ("x", "y", "1234")
    assert (await store.get(ws, user)).api_key == KEY


async def test_delete_removes_row() -> None:
    store, _ = _store()
    ws, user = uuid4(), uuid4()
    await store.set(ws, user, provider="openai", api_key=KEY, model="m", chat_model="c")
    await store.delete(ws, user)
    assert await store.get_entry(ws, user) is None


class _RaceyColl(_FakeColl):
    """First upsert loses the unique-index race; the retry must succeed."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def replace_one(self, q: dict, doc: dict, upsert: bool = False) -> None:
        self.calls += 1
        if self.calls == 1:
            raise DuplicateKeyError("E11000 duplicate key")
        await super().replace_one(q, doc, upsert=upsert)


async def test_set_retries_once_on_duplicate_key_race() -> None:
    store, coll = _store(_RaceyColl())
    ws, user = uuid4(), uuid4()
    await store.set(ws, user, provider="openai", api_key=KEY, model="m", chat_model="c")
    assert coll.calls == 2
    assert (await store.get_entry(ws, user)).key_last4 == "1234"


async def test_undecryptable_row_resolves_to_none_but_entry_survives() -> None:
    store, coll = _store()
    ws, user = uuid4(), uuid4()
    await store.set(ws, user, provider="openai", api_key=KEY, model="m", chat_model="c")
    store._fernet = Fernet(Fernet.generate_key())  # secret rotated without re-keying
    assert await store.get(ws, user) is None
    assert (await store.get_entry(ws, user)).key_last4 == "1234"


async def test_unresolvable_provider_resolves_to_none_but_entry_survives() -> None:
    store, coll = _store()
    ws, user = uuid4(), uuid4()
    await store.set(ws, user, provider="openai", api_key=KEY, model="m", chat_model="c")
    coll.docs[(str(ws), str(user))]["provider"] = "azure"  # not in PRESETS
    assert await store.get(ws, user) is None
    assert (await store.get_entry(ws, user)).provider == "azure"


async def test_ensure_indexes_creates_unique_ws_user_index() -> None:
    store, coll = _store()
    await store.ensure_indexes()
    keys, kw = coll.indexes[0]
    assert keys == [("workspace_id", 1), ("user_id", 1)]
    assert kw["unique"] is True


def test_entry_doc_and_back() -> None:
    fernet = Fernet(Fernet.generate_key())
    doc = _entry_doc(uuid4(), uuid4(), provider="openai", api_key=KEY, model="m", chat_model="c", fernet=fernet)
    assert doc["api_key_enc"] != KEY and KEY not in doc["api_key_enc"]
    assert fernet.decrypt(doc["api_key_enc"].encode()).decode() == KEY
    assert _doc_to_entry(doc).key_last4 == "1234"
    assert doc["updated_at"] is not None


def test_user_llm_fernet_requires_a_valid_secret() -> None:
    with pytest.raises(ValueError, match="USER_LLM_KEYS_SECRET"):
        user_llm_fernet(None)
    with pytest.raises(ValueError, match="USER_LLM_KEYS_SECRET"):
        user_llm_fernet("not-a-fernet-key")
    assert isinstance(user_llm_fernet(Fernet.generate_key().decode()), Fernet)
