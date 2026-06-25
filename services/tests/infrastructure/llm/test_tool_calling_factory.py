from __future__ import annotations

from types import SimpleNamespace

from infrastructure.llm import factory
from infrastructure.llm.adapters.tool_calling_adapter import (
    NativeToolCallingAdapter,
    ReactToolCallingAdapter,
)


def _settings(**overrides):
    base = {
        "llm_provider": "ollama",
        "llm_model_name": "gemma4:27b",
        "llm_base_url": "http://localhost:11434",
        "llm_api_key": None,
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
        "chat_agent_tool_calling_mode": "auto",
        "langfuse_public_key": None,
        "langfuse_secret_key": None,
        "langfuse_host": "",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_auto_uses_native_for_ollama() -> None:
    adapter = factory.create_tool_calling_llm_client(_settings())
    assert isinstance(adapter, NativeToolCallingAdapter)
    assert adapter.supports_native_tools is True


def test_explicit_react_uses_react() -> None:
    adapter = factory.create_tool_calling_llm_client(
        _settings(chat_agent_tool_calling_mode="react"),
    )
    assert isinstance(adapter, ReactToolCallingAdapter)
    assert adapter.supports_native_tools is False


def test_native_for_anthropic_under_auto() -> None:
    adapter = factory.create_tool_calling_llm_client(
        _settings(chat_llm_provider="anthropic", anthropic_api_key="k"),
    )
    assert isinstance(adapter, NativeToolCallingAdapter)
    assert adapter._provider == "anthropic"
