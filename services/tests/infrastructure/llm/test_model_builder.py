from __future__ import annotations

import pytest

from infrastructure.llm import model_builder


@pytest.fixture
def capture(monkeypatch):
    seen: dict = {}

    def fake_init(**kwargs):
        seen.clear()
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(model_builder, "init_chat_model", fake_init)
    return seen


def test_ollama_passes_base_url_no_key(capture) -> None:
    model_builder.build_chat_model(
        provider="ollama", model_name="gemma4:27b", temperature=0.1,
        base_url="http://host:11434",
    )
    assert capture["model"] == "gemma4:27b"
    assert capture["model_provider"] == "ollama"
    assert capture["base_url"] == "http://host:11434"
    assert "api_key" not in capture


def test_openai_maps_to_provider_and_key(capture) -> None:
    model_builder.build_chat_model(
        provider="openai", model_name="gpt-5", temperature=0.2, api_key="sk",
        allow_cloud=True,
    )
    assert capture["model_provider"] == "openai"
    assert capture["api_key"] == "sk"


def test_openai_sets_stream_usage(capture) -> None:
    model_builder.build_chat_model(
        provider="openai", model_name="gpt-5", temperature=0.1, api_key="sk",
        allow_cloud=True,
    )
    assert capture["stream_usage"] is True


def test_gemini_uses_google_genai_and_google_api_key(capture) -> None:
    model_builder.build_chat_model(
        provider="gemini", model_name="gemini-2.5", temperature=0.2, api_key="g",
        allow_cloud=True,
    )
    assert capture["model_provider"] == "google_genai"
    assert capture["google_api_key"] == "g"


def test_anthropic_reasoning_enables_thinking_and_forces_temp(capture) -> None:
    model_builder.build_chat_model(
        provider="anthropic", model_name="claude-sonnet-4-6", temperature=0.1,
        api_key="k", reasoning="high", allow_cloud=True,
    )
    assert capture["thinking"] == {"type": "enabled", "budget_tokens": 2048}
    assert capture["temperature"] == 1.0


def test_cloud_guard_refuses_when_disabled(capture) -> None:
    with pytest.raises(ValueError, match="disabled"):
        model_builder.build_chat_model(
            provider="anthropic", model_name="claude", temperature=0.1,
            api_key="k", allow_cloud=False,
        )


def test_ollama_allowed_when_cloud_disabled(capture) -> None:
    model_builder.build_chat_model(
        provider="ollama", model_name="gemma4:27b", temperature=0.1,
        allow_cloud=False,
    )
    assert capture["model_provider"] == "ollama"


def test_cloud_refused_by_default(capture) -> None:
    # allow_cloud defaults to False (fail-closed) — a forgotten flag must not
    # let a cloud provider through.
    with pytest.raises(ValueError, match="disabled"):
        model_builder.build_chat_model(
            provider="anthropic", model_name="claude", temperature=0.1, api_key="k",
        )


def test_cloud_requires_api_key(capture) -> None:
    from domain.exceptions import LLMNotConfiguredError

    with pytest.raises(LLMNotConfiguredError):
        model_builder.build_chat_model(
            provider="openai", model_name="gpt-5", temperature=0.1, allow_cloud=True,
        )
    assert capture == {}  # never reached init_chat_model


def test_openai_forwards_base_url(capture) -> None:
    model_builder.build_chat_model(
        provider="openai", model_name="gpt-5", temperature=0.1, api_key="sk",
        base_url="https://openrouter.ai/api/v1", allow_cloud=True,
    )
    assert capture["base_url"] == "https://openrouter.ai/api/v1"


def test_gemini_forwards_base_url(capture) -> None:
    model_builder.build_chat_model(
        provider="gemini", model_name="g", temperature=0.1, api_key="g",
        base_url="https://proxy.example/v1", allow_cloud=True,
    )
    assert capture["base_url"] == "https://proxy.example/v1"


def test_cloud_without_base_url_omits_it(capture) -> None:
    model_builder.build_chat_model(
        provider="openai", model_name="gpt-5", temperature=0.1, api_key="sk", allow_cloud=True,
    )
    assert "base_url" not in capture


def test_unknown_provider_raises(capture) -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        model_builder.build_chat_model(
            provider="grok", model_name="x", temperature=0.1,
        )


@pytest.mark.parametrize("env_var", ["OPENAI_BASE_URL", "OPENAI_API_BASE"])
def test_endpoint_host_resolves_the_env_redirect_the_sdk_would_take(env_var, monkeypatch) -> None:
    """No base_url for openai means the SDK reads the process env, so the build log
    must name the host we actually reach -- not nothing.
    """
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    assert model_builder._endpoint_host("openai", None) is None

    monkeypatch.setenv(env_var, "https://openrouter.ai/api/v1")
    assert model_builder._endpoint_host("openai", None) == "openrouter.ai"
    # An explicit base_url wins, and the env never leaks into another provider.
    assert model_builder._endpoint_host("openai", "https://gw.internal/v1") == "gw.internal"
    assert model_builder._endpoint_host("anthropic", None) is None


def test_endpoint_host_logs_no_credentials(monkeypatch) -> None:
    """Host only -- a base URL can carry a key in userinfo or the query string."""
    monkeypatch.setenv("OPENAI_BASE_URL", "https://user:sk-secret@gw.example/v1?token=sk-abc")
    assert model_builder._endpoint_host("openai", None) == "gw.example"
