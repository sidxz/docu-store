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


def test_user_llm_keys_flag_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _isolated_settings(monkeypatch, "USER_LLM_KEYS_ENABLED")
    assert s.user_llm_keys_enabled is False


def test_user_llm_keys_flag_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from cryptography.fernet import Fernet

    monkeypatch.setenv("USER_LLM_KEYS_ENABLED", "true")
    monkeypatch.setenv("USER_LLM_KEYS_SECRET", Fernet.generate_key().decode())
    assert Settings(_env_file=None).user_llm_keys_enabled is True


def test_user_llm_keys_secret_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _isolated_settings(monkeypatch, "USER_LLM_KEYS_SECRET")
    assert s.user_llm_keys_secret is None


def test_user_llm_providers_collection_default(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _isolated_settings(monkeypatch, "MONGO_USER_LLM_PROVIDERS_COLLECTION")
    assert s.mongo_user_llm_providers_collection == "user_llm_providers"


def test_flag_on_without_secret_fails_settings_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("USER_LLM_KEYS_ENABLED", "USER_LLM_KEYS_SECRET"):
        monkeypatch.delenv(name, raising=False)
    # Settings has no populate_by_name — only the validation_alias (the env
    # var name) is a valid init kwarg, not the snake_case field name.
    with pytest.raises(ValueError, match="USER_LLM_KEYS_SECRET"):
        Settings(_env_file=None, USER_LLM_KEYS_ENABLED=True, USER_LLM_KEYS_SECRET=None)
    with pytest.raises(ValueError, match="not a valid Fernet key"):
        Settings(_env_file=None, USER_LLM_KEYS_ENABLED=True, USER_LLM_KEYS_SECRET="nope")


def test_flag_on_with_valid_secret_constructs(monkeypatch: pytest.MonkeyPatch) -> None:
    from cryptography.fernet import Fernet

    for name in ("USER_LLM_KEYS_ENABLED", "USER_LLM_KEYS_SECRET"):
        monkeypatch.delenv(name, raising=False)
    s = Settings(_env_file=None, USER_LLM_KEYS_ENABLED=True, USER_LLM_KEYS_SECRET=Fernet.generate_key().decode())
    assert s.user_llm_keys_enabled is True


def test_flag_off_needs_no_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("USER_LLM_KEYS_ENABLED", "USER_LLM_KEYS_SECRET"):
        monkeypatch.delenv(name, raising=False)
    assert Settings(_env_file=None).user_llm_keys_secret is None
