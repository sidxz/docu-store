from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from application.ports.user_llm_config import UserLLMConfig
from application.services.llm_scope import UserLLMScope, workspace_scope
from domain.aggregates.artifact import Artifact
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from infrastructure.llm.llm_context import get_user_config

CFG = UserLLMConfig(provider="openai", api_key="k")


class FakeStore:
    def __init__(self, config: UserLLMConfig | None = CFG) -> None:
        self.config = config
        self.calls: list[UUID] = []

    async def get(self, workspace_id: UUID) -> UserLLMConfig | None:
        self.calls.append(workspace_id)
        return self.config


def _artifact(ws: UUID, owner: UUID) -> Artifact:
    return Artifact.create(
        source_uri=None, source_filename="a.pdf", artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF, storage_location="/a.pdf", workspace_id=ws, owner_id=owner,
    )


async def test_enabled_sets_config_for_the_block_and_resets() -> None:
    store = FakeStore()
    ws = uuid4()
    async with UserLLMScope(store, enabled=True).for_workspace(ws) as cfg:
        assert cfg is CFG
        assert get_user_config() is CFG
    assert get_user_config() is None
    assert store.calls == [ws]


async def test_disabled_never_touches_store() -> None:
    store = FakeStore()
    async with UserLLMScope(store, enabled=False).for_workspace(uuid4()) as cfg:
        assert cfg is None
        assert get_user_config() is None
    assert store.calls == []


async def test_missing_workspace_skips_lookup() -> None:
    store = FakeStore()
    async with UserLLMScope(store, enabled=True).for_workspace(None):
        assert get_user_config() is None
    assert store.calls == []


async def test_workspace_scope_uses_the_aggregates_workspace_not_its_uploader() -> None:
    ws = uuid4()
    store = FakeStore()
    scope = UserLLMScope(store, enabled=True)
    async with workspace_scope(scope, _artifact(ws, uuid4())):
        assert get_user_config() is CFG
    assert store.calls == [ws]


async def test_workspace_scope_without_scope_is_noop() -> None:
    async with workspace_scope(None, _artifact(uuid4(), uuid4())):
        assert get_user_config() is None


async def test_config_reaches_task_created_inside_scope() -> None:
    async def read() -> UserLLMConfig | None:
        return get_user_config()

    async with UserLLMScope(FakeStore(), enabled=True).for_workspace(uuid4()):
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
    ws = uuid4()
    assert await store.get(ws) is None
    assert await store.get_entry(ws) is None
    assert await store.list_entries(ws) == []
    assert await store.get_config(ws, "openai") is None
    assert await store.update_models(ws, provider="openai", model="m", chat_model="c") is False
    assert await store.activate(ws, "openai") is False
    assert await store.delete(ws, "openai") is False
    await store.ensure_indexes()  # no-op
    with pytest.raises(RuntimeError, match="USER_LLM_KEYS_ENABLED"):
        await store.set(ws, provider="openai", api_key="k", model="m", chat_model="c")
