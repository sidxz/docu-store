"""Provider wiring for the StructfloNERExtractor adapter.

The adapter builds the structflo LLM extractor per call from the effective
config (caller's UserLLMConfig → constructor defaults), forwards base URLs to
providers that accept them, fails closed without a key, and lets provider
failures escape (no `[]`-as-success).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.ports.user_llm_config import UserLLMConfig
from domain.exceptions import LLMAuthError, LLMNotConfiguredError
from infrastructure.llm import llm_context
from infrastructure.ner.structflo_ner_extractor import StructfloNERExtractor


@pytest.fixture
def stub_structflo(monkeypatch):
    """Patch the structflo symbols the adapter imports (init + per-call)."""
    fake_ner_cls = MagicMock(name="NERExtractor")
    monkeypatch.setattr("structflo.ner.NERExtractor", fake_ner_cls)
    monkeypatch.setattr("structflo.ner.fast.FastNERExtractor", MagicMock())
    monkeypatch.setattr("structflo.ner.TB", object())
    return fake_ner_cls


def _kwargs(fake_cls) -> dict:
    _, kwargs = fake_cls.call_args
    return kwargs


def test_init_does_not_build_llm_extractor(stub_structflo):
    StructfloNERExtractor(model_id="gemma3:27b", provider="ollama", model_url="http://ollama:11434")
    stub_structflo.assert_not_called()


def test_ollama_forwards_model_url(stub_structflo):
    ex = StructfloNERExtractor(model_id="medgemma:latest", provider="ollama", model_url="http://ollama:11434")
    ex._llm_extractor()
    kw = _kwargs(stub_structflo)
    assert kw["provider"] == "ollama"
    assert kw["model_url"] == "http://ollama:11434"
    assert kw["model_id"] == "medgemma:latest"


def test_openai_forwards_model_url(stub_structflo):
    ex = StructfloNERExtractor(
        model_id="gpt-4o", provider="openai", api_key="sk-x", model_url="https://openrouter.ai/api/v1",
    )
    ex._llm_extractor()
    kw = _kwargs(stub_structflo)
    assert kw["provider"] == "openai"
    assert kw["api_key"] == "sk-x"
    assert kw["model_url"] == "https://openrouter.ai/api/v1"


def test_gemini_drops_model_url(stub_structflo):
    ex = StructfloNERExtractor(model_id="gemini-2.5", provider="gemini", api_key="g", model_url="http://x")
    ex._llm_extractor()
    assert _kwargs(stub_structflo)["model_url"] is None


def test_unsupported_provider_degrades_to_fast_only(stub_structflo):
    ex = StructfloNERExtractor(model_id="claude-x", provider="anthropic", api_key="k")
    assert ex._llm_extractor() is None
    stub_structflo.assert_not_called()


def test_keyless_cloud_fails_closed(stub_structflo):
    ex = StructfloNERExtractor(model_id="gpt-4o", provider="openai")
    with pytest.raises(LLMNotConfiguredError):
        ex._llm_extractor()
    stub_structflo.assert_not_called()


def test_user_config_overrides_provider_key_url_and_model(stub_structflo):
    ex = StructfloNERExtractor(model_id="gemma3:27b", provider="ollama", model_url="http://ollama:11434")
    cfg = UserLLMConfig(
        provider="openai", api_key="sk-u", base_url="https://openrouter.ai/api/v1", model="gpt-5-mini",
    )
    tok = llm_context.set_user_config(cfg)
    try:
        ex._llm_extractor()
    finally:
        llm_context.reset_user_config(tok)
    kw = _kwargs(stub_structflo)
    assert (kw["provider"], kw["api_key"], kw["model_url"], kw["model_id"]) == (
        "openai", "sk-u", "https://openrouter.ai/api/v1", "gpt-5-mini",
    )


def test_user_config_without_model_keeps_default_model(stub_structflo):
    ex = StructfloNERExtractor(model_id="gemma3:27b", provider="ollama")
    tok = llm_context.set_user_config(UserLLMConfig(provider="ollama"))
    try:
        ex._llm_extractor()
    finally:
        llm_context.reset_user_config(tok)
    assert _kwargs(stub_structflo)["model_id"] == "gemma3:27b"


def test_init_registers_langextract_providers_for_llm_path(stub_structflo, monkeypatch):
    """langextract 1.1.1's explicit-provider factory path skips
    load_builtins_once(), so a fresh worker process has an empty registry and
    every LLM extract dies with InferenceConfigError("ollama"). Adapter init
    must ensure the builtin providers are registered."""
    import langextract.providers as lx_providers
    from langextract.providers import router

    router.clear()
    monkeypatch.setattr(lx_providers, "_builtins_loaded", False)
    try:
        StructfloNERExtractor(model_id="gemma3:27b", provider="ollama", model_url="http://x")
        assert router.resolve_provider("ollama") is not None
    finally:
        lx_providers.load_builtins_once()


async def test_llm_failure_propagates_typed(stub_structflo):
    class _Boom(Exception):
        status_code = 401

    stub_structflo.return_value.extract.side_effect = _Boom("bad key")
    ex = StructfloNERExtractor(model_id="gpt-4o", provider="openai", api_key="sk")
    with pytest.raises(LLMAuthError):
        await ex.extract("some text")


async def test_unknown_llm_failure_still_propagates(stub_structflo):
    stub_structflo.return_value.extract.side_effect = RuntimeError("ollama down")
    ex = StructfloNERExtractor(model_id="gemma3:27b", provider="ollama")
    with pytest.raises(RuntimeError):
        await ex.extract("some text")
