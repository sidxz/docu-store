from __future__ import annotations

import pytest

from infrastructure.config import Settings


def test_cloud_guard_defaults_on() -> None:
    s = Settings()
    assert s.allow_cloud_llm is True


def test_new_provider_and_key_fields_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    # Set env vars to override .env file values
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.setenv("GOOGLE_API_KEY", "goog")
    monkeypatch.setenv("ALLOW_CLOUD_LLM", "false")
    monkeypatch.setenv("LLM_REASONING", "high")

    s = Settings()
    assert s.llm_provider == "anthropic"
    assert s.anthropic_api_key == "sk-ant"
    assert s.google_api_key == "goog"
    assert s.allow_cloud_llm is False
    assert s.llm_reasoning == "high"


def test_reasoning_default_off() -> None:
    s = Settings()
    assert s.llm_reasoning == "off"
    assert s.chat_llm_reasoning == "off"
