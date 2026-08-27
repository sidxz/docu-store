from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from application.ports.user_llm_config import UserLLMConfig
from application.services.llm_scope import UserLLMScope, owner_scope
from domain.aggregates.artifact import Artifact
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from infrastructure.llm.llm_context import get_user_config

CFG = UserLLMConfig(provider="openai", api_key="k")


class FakeStore:
    def __init__(self, config: UserLLMConfig | None = CFG) -> None:
        self.config = config
        self.calls: list[tuple[UUID, UUID]] = []

    async def get(self, workspace_id: UUID, user_id: UUID) -> UserLLMConfig | None:
        self.calls.append((workspace_id, user_id))
        return self.config


def _artifact(ws: UUID, owner: UUID) -> Artifact:
    return Artifact.create(
        source_uri=None, source_filename="a.pdf", artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF, storage_location="/a.pdf", workspace_id=ws, owner_id=owner,
    )


async def test_enabled_sets_config_for_the_block_and_resets() -> None:
    store = FakeStore()
    ws, user = uuid4(), uuid4()
    async with UserLLMScope(store, enabled=True).for_user(ws, user) as cfg:
        assert cfg is CFG
        assert get_user_config() is CFG
    assert get_user_config() is None
    assert store.calls == [(ws, user)]


async def test_disabled_never_touches_store() -> None:
    store = FakeStore()
    async with UserLLMScope(store, enabled=False).for_user(uuid4(), uuid4()) as cfg:
        assert cfg is None
        assert get_user_config() is None
    assert store.calls == []


async def test_missing_identity_skips_lookup() -> None:
    store = FakeStore()
    async with UserLLMScope(store, enabled=True).for_user(uuid4(), None):
        assert get_user_config() is None
    assert store.calls == []


async def test_for_owner_uses_artifact_identity() -> None:
    ws, owner = uuid4(), uuid4()
    store = FakeStore()
    async with UserLLMScope(store, enabled=True).for_owner(_artifact(ws, owner)):
        assert get_user_config() is CFG
    assert store.calls == [(ws, owner)]


async def test_owner_scope_without_scope_is_noop() -> None:
    async with owner_scope(None, _artifact(uuid4(), uuid4())):
        assert get_user_config() is None


async def test_config_reaches_task_created_inside_scope() -> None:
    async def read() -> UserLLMConfig | None:
        return get_user_config()

    async with UserLLMScope(FakeStore(), enabled=True).for_user(uuid4(), uuid4()):
        task = asyncio.create_task(read())
    assert await task is CFG


def test_container_registers_null_store_and_scope(monkeypatch) -> None:  # noqa: ANN001
    from application.ports.user_llm_config import NullUserLLMConfigStore, UserLLMConfigStore
    from infrastructure.di import container as container_module

    # Flag off regardless of the developer's .env (BYO mode swaps in the Mongo store).
    monkeypatch.setattr(container_module.settings, "user_llm_keys_enabled", False)
    container = container_module.create_container()
    assert isinstance(container[UserLLMConfigStore], NullUserLLMConfigStore)
    assert isinstance(container[UserLLMScope], UserLLMScope)


async def test_null_store_is_empty_and_refuses_writes() -> None:
    from application.ports.user_llm_config import NullUserLLMConfigStore
    import pytest

    store = NullUserLLMConfigStore()
    ws, user = uuid4(), uuid4()
    assert await store.get(ws, user) is None
    assert await store.get_entry(ws, user) is None
    assert await store.update_models(ws, user, model="m", chat_model="c") is False
    await store.delete(ws, user)  # no-op
    await store.ensure_indexes()  # no-op
    with pytest.raises(RuntimeError, match="USER_LLM_KEYS_ENABLED"):
        await store.set(ws, user, provider="openai", api_key="k", model="m", chat_model="c")
