from __future__ import annotations

import pytest

from infrastructure.config import Settings


def _isolated_settings(monkeypatch: pytest.MonkeyPatch, *names: str) -> Settings:
    """Settings with the given env vars cleared and the .env file ignored, so
    default assertions don't depend on the developer's local environment."""
    for name in names:
        monkeypatch.delenv(name, raising=False)
    return Settings(_env_file=None)


def test_cloud_guard_defaults_on(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _isolated_settings(monkeypatch, "ALLOW_CLOUD_LLM")
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


def test_reasoning_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _isolated_settings(monkeypatch, "LLM_REASONING", "CHAT_LLM_REASONING")
    assert s.llm_reasoning == "off"
    assert s.chat_llm_reasoning == "off"


def test_per_lane_reasoning_defaults_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # None means "inherit CHAT_LLM_REASONING"; the container resolves it.
    s = _isolated_settings(monkeypatch, "CHAT_SYNTHESIS_REASONING", "CHAT_RETRIEVAL_REASONING")
    assert s.chat_synthesis_reasoning is None
    assert s.chat_retrieval_reasoning is None
