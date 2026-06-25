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


def test_create_chat_llm_client_overrides_provider() -> None:
    client = factory.create_chat_llm_client(
        _settings(chat_llm_provider="openai", chat_llm_model_name="gpt-5", openai_api_key="sk"),
    )
    assert client._provider == "openai"
    assert client._model_name == "gpt-5"
    assert client._api_key == "sk"
