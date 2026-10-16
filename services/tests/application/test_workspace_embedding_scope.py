"""Which embedding model + key a workspace call resolves to (self-serve)."""

from __future__ import annotations

from uuid import uuid4

from application.ports.user_llm_config import UserLLMConfig, UserLLMProviderEntry
from application.ports.workspace_embedding_config import WorkspaceEmbeddingConfig
from application.services.llm_providers import OPENROUTER_BASE_URL
from application.services.llm_scope import UserLLMScope
from infrastructure.llm import llm_context

WS = uuid4()


class FakeEmbeddingStore:
    def __init__(self, model: str | None) -> None:
        self.model = model

    async def get(self, workspace_id):
        return WorkspaceEmbeddingConfig(model=self.model) if self.model else None


class FakeLLMStore:
    """The workspace's keys by provider id; ``active`` names the active one."""

    def __init__(self, keys: dict[str, str], active: str | None = None) -> None:
        self.keys = keys
        self.active = active

    async def get(self, workspace_id):
        return None

    async def get_entry(self, workspace_id):
        if self.active is None:
            return None
        return UserLLMProviderEntry(self.active, "m", "c", "1234", active=True)

    async def get_config(self, workspace_id, provider):
        key = self.keys.get(provider)
        return UserLLMConfig(provider="openai", api_key=key) if key else None


def _scope(model, keys=None, active=None, *, store=True) -> UserLLMScope:
    return UserLLMScope(
        FakeLLMStore(keys or {}, active),
        enabled=True,
        embedding_store=FakeEmbeddingStore(model) if store else None,
    )


async def test_server_model_when_unset_local_or_no_store() -> None:
    assert await _scope(None).embedding_spec(WS) is None
    assert await _scope("local").embedding_spec(WS) is None
    assert await _scope("openai/text-embedding-3-small", store=False).embedding_spec(WS) is None


async def test_openrouter_key_serves_openai_model() -> None:
    spec = await _scope("openai/text-embedding-3-small", {"openrouter": "or-key"}).embedding_spec(WS)
    assert spec.model == "openai/text-embedding-3-small"
    assert (spec.sdk, spec.provider_model, spec.base_url) == (
        "openai", "openai/text-embedding-3-small", OPENROUTER_BASE_URL,
    )
    assert spec.api_key == "or-key"
    assert spec.missing_key_message is None


async def test_active_provider_is_preferred() -> None:
    keys = {"openai": "oa-key", "openrouter": "or-key"}
    spec = await _scope("openai/text-embedding-3-small", keys).embedding_spec(WS)
    assert spec.api_key == "oa-key"  # direct provider first by default
    spec = await _scope("openai/text-embedding-3-small", keys, "openrouter").embedding_spec(WS)
    assert spec.api_key == "or-key"


async def test_gemini_model_carries_its_task_prefixes() -> None:
    spec = await _scope("google/gemini-embedding-2", {"gemini": "g-key"}).embedding_spec(WS)
    assert (spec.sdk, spec.provider_model, spec.base_url) == ("gemini", "gemini-embedding-2", None)
    assert spec.query_prefix.startswith("task: search result")
    assert spec.document_prefix.startswith("title: none")


async def test_no_compatible_key_fails_closed_with_guidance() -> None:
    # A Gemini key cannot serve an OpenAI model — never fall back to the server model.
    spec = await _scope("openai/text-embedding-3-small", {"gemini": "g-key"}).embedding_spec(WS)
    assert spec is not None
    assert spec.api_key is None
    assert "OpenAI or OpenRouter" in spec.missing_key_message


async def test_unknown_stored_model_fails_closed() -> None:
    spec = await _scope("acme/retired-model", {"openai": "k"}).embedding_spec(WS)
    assert "no longer supported" in spec.missing_key_message


async def test_for_user_sets_and_resets_the_embedding_context() -> None:
    assert llm_context.get_embedding_spec() is llm_context.NOT_SCOPED
    async with _scope("openai/text-embedding-3-small", {"openai": "k"}).for_workspace(WS):
        assert llm_context.get_embedding_spec().api_key == "k"
    assert llm_context.get_embedding_spec() is llm_context.NOT_SCOPED
    async with _scope(None).for_workspace(WS):
        assert llm_context.get_embedding_spec() is None
