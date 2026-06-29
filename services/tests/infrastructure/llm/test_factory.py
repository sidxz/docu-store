from __future__ import annotations

from types import SimpleNamespace

import pytest

from infrastructure.llm import factory
from infrastructure.llm.adapters.langchain_llm_client import LangChainLLMClient


def _settings(**overrides):
    base = {
        "llm_provider": "ollama",
        "llm_model_name": "gemma4:27b",
        "llm_base_url": "http://localhost:11434",
        "llm_api_key": None,
        "llm_temperature": 0.1,
        "llm_reasoning": "off",
        "llm_num_ctx": 32768,
        "openai_api_key": None,
        "anthropic_api_key": None,
        "google_api_key": None,
        "allow_cloud_llm": True,
        "chat_llm_provider": None,
        "chat_llm_model_name": None,
        "chat_llm_base_url": None,
        "chat_llm_api_key": None,
        "chat_llm_temperature": 0.3,
        "chat_llm_reasoning": "off",
        "chat_synthesis_reasoning": None,
        "chat_retrieval_reasoning": None,
        "langfuse_public_key": None,
        "langfuse_secret_key": None,
        "langfuse_host": "",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_create_llm_client_returns_generic_ollama() -> None:
    client = factory.create_llm_client(_settings())
    assert isinstance(client, LangChainLLMClient)
    assert client._provider == "ollama"
    assert client._allow_cloud is True


def test_create_llm_client_resolves_anthropic_key() -> None:
    client = factory.create_llm_client(
        _settings(llm_provider="anthropic", anthropic_api_key="sk-ant"),
    )
    assert client._provider == "anthropic"
    assert client._api_key == "sk-ant"


def test_create_chat_llm_client_falls_back_to_batch() -> None:
    client = factory.create_chat_llm_client(_settings(llm_model_name="gemma4:27b"))
    assert isinstance(client, LangChainLLMClient)
    assert client._model_name == "gemma4:27b"  # inherited from batch
    assert client._reasoning == "off"


def test_create_chat_llm_client_reasoning_override() -> None:
    # The container passes a resolved reasoning level for the synthesis client.
    client = factory.create_chat_llm_client(_settings(chat_llm_reasoning="off"), reasoning="high")
    assert client._reasoning == "high"


def test_create_chat_llm_client_reasoning_defaults_to_base() -> None:
    client = factory.create_chat_llm_client(_settings(chat_llm_reasoning="medium"))
    assert client._reasoning == "medium"


def test_create_chat_llm_client_overrides_provider() -> None:
    client = factory.create_chat_llm_client(
        _settings(chat_llm_provider="openai", chat_llm_model_name="gpt-5", openai_api_key="sk"),
    )
    assert client._provider == "openai"
    assert client._model_name == "gpt-5"
    assert client._api_key == "sk"


def test_create_llm_client_raises_when_cloud_key_missing() -> None:
    with pytest.raises(ValueError, match="API key"):
        factory.create_llm_client(_settings(llm_provider="anthropic"))


def test_resolve_api_key_uses_generic_llm_api_key_fallback() -> None:
    client = factory.create_llm_client(
        _settings(llm_provider="openai", openai_api_key=None, llm_api_key="generic-key"),
    )
    assert client._api_key == "generic-key"


def test_create_llm_client_refuses_cloud_when_disabled() -> None:
    with pytest.raises(ValueError, match="disabled"):
        factory.create_llm_client(
            _settings(llm_provider="anthropic", anthropic_api_key="k", allow_cloud_llm=False),
        )


def test_create_chat_llm_client_refuses_cloud_when_disabled() -> None:
    with pytest.raises(ValueError, match="disabled"):
        factory.create_chat_llm_client(
            _settings(chat_llm_provider="openai", openai_api_key="k", allow_cloud_llm=False),
        )


def test_ollama_allowed_when_cloud_disabled() -> None:
    client = factory.create_llm_client(_settings(allow_cloud_llm=False))
    assert client._provider == "ollama"
