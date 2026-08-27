"""Explicit reasoning-off for OpenAI gpt-5.x: the provider otherwise applies a default effort."""

from __future__ import annotations

from infrastructure.llm.model_builder import _reasoning_kwargs


def test_gpt5x_off_is_sent_explicitly() -> None:
    assert _reasoning_kwargs("openai", None, "gpt-5.6-luna") == {"reasoning_effort": "none"}
    assert _reasoning_kwargs("openai", "off", "gpt-5.1") == {"reasoning_effort": "none"}


def test_openrouter_slug_is_recognised() -> None:
    assert _reasoning_kwargs("openai", None, "openai/gpt-5.2-pro") == {"reasoning_effort": "none"}


def test_other_openai_models_are_untouched() -> None:
    for name in ("gpt-5", "gpt-5-mini", "gpt-5-chat-latest", "gpt-4.1", "o3-mini"):
        assert _reasoning_kwargs("openai", None, name) == {}, name


def test_reasoning_on_and_other_providers_unchanged() -> None:
    assert _reasoning_kwargs("openai", "medium", "gpt-5.6-luna") == {"reasoning_effort": "medium"}
    assert _reasoning_kwargs("ollama", None, "gpt-5.6-luna") == {}
    assert _reasoning_kwargs("gemini", None, "gpt-5.6-luna") == {}
