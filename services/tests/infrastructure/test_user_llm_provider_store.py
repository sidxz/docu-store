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
    """Documents in a list, matched by a tiny subset of Mongo's query language."""

    def __init__(self) -> None:
        self.docs: list[dict] = []
        self.indexes: list = []
        self.dropped: list[str] = []

    @staticmethod
    def _matches(doc: dict, q: dict) -> bool:
        for field, want in q.items():
            got = doc.get(field)
            if isinstance(want, dict):
                if "$ne" in want and got == want["$ne"]:
                    return False
                if "$exists" in want and (field in doc) != want["$exists"]:
                    return False
            elif got != want:
                return False
        return True

    def _all(self, q: dict) -> list[dict]:
        return [d for d in self.docs if self._matches(d, q)]

    async def find_one(self, q: dict) -> dict | None:
        found = self._all(q)
        return found[0] if found else None

    def find(self, q: dict) -> _FakeCursor:
        return _FakeCursor(self._all(q))

    async def replace_one(self, q: dict, doc: dict, upsert: bool = False) -> None:
        existing = self._all(q)
        if existing:
            self.docs[self.docs.index(existing[0])] = doc
        else:
            self.docs.append(doc)

    async def update_one(self, q: dict, update: dict):
        doc = await self.find_one(q)
        if doc is not None:
            doc.update(update["$set"])
        return type("R", (), {"matched_count": 0 if doc is None else 1})()

    async def update_many(self, q: dict, update: dict):
        hit = self._all(q)
        for doc in hit:
            doc.update(update["$set"])
        return type("R", (), {"modified_count": len(hit)})()

    async def delete_one(self, q: dict):
        found = self._all(q)
        for doc in found[:1]:
            self.docs.remove(doc)
        return type("R", (), {"deleted_count": len(found[:1])})()

    async def create_index(self, keys, **kw) -> None:
        self.indexes.append((keys, kw))

    async def index_information(self) -> dict:
        return {name: {} for _, kw in self.indexes for name in [kw.get("name")] if name}

    async def drop_index(self, name: str) -> None:
        self.dropped.append(name)
        self.indexes = [(k, kw) for k, kw in self.indexes if kw.get("name") != name]


class _FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def sort(self, field: str, direction: int) -> _FakeCursor:
        self._docs = sorted(
            self._docs, key=lambda d: d.get(field) or 0, reverse=direction < 0
        )
        return self

    async def __aiter__(self):  # noqa: PLE0302 — motor's cursor is an async iterable
        for doc in self._docs:
            yield doc


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
    assert entry.provider == "openrouter"
    assert (entry.model, entry.chat_model, entry.key_last4) == ("m", "c", "1234")
    assert entry.active is True  # the first provider added is the one that runs
    # The raw key never lands in the document.
    assert KEY not in json.dumps(coll.docs[0], default=str)


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
    assert await store.update_models(ws, user, provider="openai", model="x", chat_model="y") is False
    await store.set(ws, user, provider="openai", api_key=KEY, model="m", chat_model="c")
    assert await store.update_models(ws, user, provider="openai", model="x", chat_model="y") is True
    entry = await store.get_entry(ws, user)
    assert (entry.model, entry.chat_model, entry.key_last4) == ("x", "y", "1234")
    assert (await store.get(ws, user)).api_key == KEY


async def test_delete_removes_row() -> None:
    store, _ = _store()
    ws, user = uuid4(), uuid4()
    await store.set(ws, user, provider="openai", api_key=KEY, model="m", chat_model="c")
    assert await store.delete(ws, user, "openai") is True
    assert await store.get_entry(ws, user) is None
    assert await store.delete(ws, user, "openai") is False


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
    coll.docs[0]["provider"] = "azure"  # not in PRESETS
    assert await store.get(ws, user) is None
    assert (await store.get_entry(ws, user)).provider == "azure"


async def test_ensure_indexes_creates_the_unique_ws_user_provider_index() -> None:
    store, coll = _store()
    await store.ensure_indexes()
    keys, kw = coll.indexes[0]
    assert keys == [("workspace_id", 1), ("user_id", 1), ("provider", 1)]
    assert kw["unique"] is True


async def test_ensure_indexes_retires_the_single_slot_index() -> None:
    """The old unique (ws, user) index does not merely mislabel a registry — it
    rejects the second provider a user adds."""
    store, coll = _store()
    coll.indexes.append(([("workspace_id", 1), ("user_id", 1)], {"name": "idx_user_llm_ws_user"}))

    await store.ensure_indexes()

    assert coll.dropped == ["idx_user_llm_ws_user"]


async def test_ensure_indexes_adopts_rows_written_before_the_registry() -> None:
    """get() reads active-only, so a pre-registry row without the field would vanish."""
    store, coll = _store()
    coll.docs.append({"workspace_id": "w", "user_id": "u", "provider": "openai"})

    await store.ensure_indexes()

    assert coll.docs[0]["active"] is True


# ── A registry: adding a provider never disturbs another provider's key ──


async def test_adding_a_second_provider_keeps_the_first_and_takes_over_active() -> None:
    store, _ = _store()
    ws, user = uuid4(), uuid4()
    await store.set(ws, user, provider="openai", api_key=KEY, model="m", chat_model="c")

    await store.set(ws, user, provider="openrouter", api_key="second-key-9999", model="m2", chat_model="c2")

    entries = {e.provider: e for e in await store.list_entries(ws, user)}
    assert set(entries) == {"openai", "openrouter"}
    assert entries["openrouter"].active and not entries["openai"].active
    # The evicted provider keeps its key: switching back costs one click, not a re-paste.
    assert (await store.get_config(ws, user, "openai")).api_key == KEY


async def test_activate_switches_which_config_resolves() -> None:
    store, _ = _store()
    ws, user = uuid4(), uuid4()
    await store.set(ws, user, provider="openai", api_key=KEY, model="m", chat_model="c")
    await store.set(ws, user, provider="gemini", api_key="gem-key-4321", model="g", chat_model="g")
    assert (await store.get(ws, user)).model == "g"

    assert await store.activate(ws, user, "openai") is True

    assert (await store.get(ws, user)).model == "m"
    assert await store.activate(ws, user, "openrouter") is False  # never stored


async def test_deleting_the_active_provider_leaves_the_rest_stored_but_nothing_running() -> None:
    store, _ = _store()
    ws, user = uuid4(), uuid4()
    await store.set(ws, user, provider="openai", api_key=KEY, model="m", chat_model="c")
    await store.set(ws, user, provider="gemini", api_key="gem-key-4321", model="g", chat_model="g")

    await store.delete(ws, user, "gemini")

    assert await store.get(ws, user) is None
    assert await store.get_entry(ws, user) is None
    assert [e.provider for e in await store.list_entries(ws, user)] == ["openai"]


async def test_get_config_reads_an_inactive_provider_so_it_can_be_tested_first() -> None:
    store, _ = _store()
    ws, user = uuid4(), uuid4()
    await store.set(ws, user, provider="openai", api_key=KEY, model="m", chat_model="c")
    await store.set(ws, user, provider="gemini", api_key="gem-key-4321", model="g", chat_model="g")

    cfg = await store.get_config(ws, user, "openai")

    assert cfg is not None and cfg.api_key == KEY and cfg.model == "m"


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
