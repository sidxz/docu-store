from __future__ import annotations

import pytest

from application.ports.user_llm_config import UserLLMConfig
from domain.exceptions import LLMNotConfiguredError
from infrastructure.llm import llm_context, model_builder, reasoning_context
from infrastructure.llm.model_spec import ModelCache, ModelSpec, effective_spec

ENV = ModelSpec(
    provider="ollama", model_name="gemma4:31b", temperature=0.1,
    base_url="http://ollama:11434", reasoning="off", num_ctx=32768, allow_cloud=True,
)
USER = UserLLMConfig(
    provider="openai", api_key="sk-u", base_url="https://openrouter.ai/api/v1",
    model="gpt-5-mini", chat_model="gpt-5",
)


def test_no_user_config_returns_env_defaults() -> None:
    assert effective_spec(ENV, None) == ENV
    assert effective_spec(ENV, "synthesis") == ENV


def test_user_config_overrides_provider_key_url_and_model_per_lane() -> None:
    tok = llm_context.set_user_config(USER)
    try:
        batch = effective_spec(ENV, None)
        chat = effective_spec(ENV, "synthesis")
    finally:
        llm_context.reset_user_config(tok)
    assert (batch.provider, batch.api_key, batch.base_url, batch.model_name) == (
        "openai", "sk-u", "https://openrouter.ai/api/v1", "gpt-5-mini",
    )
    assert chat.model_name == "gpt-5"
    # env-only knobs survive the overlay
    assert batch.temperature == ENV.temperature
    assert batch.num_ctx == ENV.num_ctx
    assert batch.allow_cloud is True


def test_user_config_without_models_keeps_env_model() -> None:
    tok = llm_context.set_user_config(UserLLMConfig(provider="openai", api_key="k"))
    try:
        assert effective_spec(ENV, "base").model_name == ENV.model_name
        assert effective_spec(ENV, "base").base_url is None  # never the Ollama URL
    finally:
        llm_context.reset_user_config(tok)


def test_lane_reasoning_override_applies_on_top() -> None:
    tok = reasoning_context.set_reasoning_override({"synthesis": "high"})
    try:
        assert effective_spec(ENV, "synthesis").reasoning == "high"
        assert effective_spec(ENV, None).reasoning == "off"
    finally:
        reasoning_context.reset_reasoning_override(tok)


def test_spec_repr_hides_key() -> None:
    spec = ModelSpec(provider="openai", model_name="m", temperature=0.1, api_key="sk-u")
    assert "sk-u" not in repr(spec)


def test_cache_builds_once_per_spec_and_is_bounded(monkeypatch) -> None:
    built: list[ModelSpec] = []
    monkeypatch.setattr(
        model_builder, "build_chat_model", lambda **kw: built.append(ModelSpec(**kw)) or object(),
    )
    cache = ModelCache(maxsize=2)
    a = ModelSpec(provider="openai", model_name="m", temperature=0.1, api_key="k1", allow_cloud=True)
    b = ModelSpec(provider="openai", model_name="m", temperature=0.1, api_key="k2", allow_cloud=True)
    c = ModelSpec(provider="openai", model_name="m", temperature=0.1, api_key="k3", allow_cloud=True)
    assert cache.get(a) is cache.get(a)
    cache.get(b)
    assert len(built) == 2  # different key → different fingerprint → second build
    cache.get(c)
    assert len(cache) == 2  # bounded: `a` evicted
    cache.get(a)
    assert len(built) == 4


def test_cloud_without_key_raises_not_configured_at_build() -> None:
    with pytest.raises(LLMNotConfiguredError):
        ModelCache().get(ModelSpec(provider="openai", model_name="m", temperature=0.1, allow_cloud=True))
