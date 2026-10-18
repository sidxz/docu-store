"""Provider presets — the single place BYO model defaults live."""

from __future__ import annotations

from application.services.llm_providers import OPENROUTER_BASE_URL, PRESETS


def test_presets_cover_the_user_facing_providers() -> None:
    assert set(PRESETS) == {"openrouter", "openai", "gemini", "tamu"}


def test_openrouter_is_openai_compatible_with_fixed_base_url() -> None:
    p = PRESETS["openrouter"]
    assert p.provider == "openai"
    assert p.base_url == OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"
    assert p.model.startswith("openai/") and p.chat_model.startswith("openai/")


def test_direct_providers_have_no_base_url_and_named_models() -> None:
    for pid in ("openai", "gemini"):
        p = PRESETS[pid]
        assert p.provider == pid
        assert p.base_url is None
        assert p.model and p.chat_model


def test_served_by_names_the_gateway_else_the_vendor() -> None:
    from application.services.llm_providers import TAMU_AI_BASE_URL, served_by

    assert served_by("openai", TAMU_AI_BASE_URL, "gpt-5.6-luna") == "TAMU AI / gpt-5.6-luna"
    assert served_by("openai", OPENROUTER_BASE_URL, "openai/gpt-5") == "OpenRouter / openai/gpt-5"
    assert served_by("openai", None, "gpt-5.4") == "OpenAI / gpt-5.4"
    assert served_by("google_genai", None, "gemini-2.5-pro") == "Gemini / gemini-2.5-pro"
    assert served_by("acme", None, "m") == "acme / m"
    assert served_by(None, None, "m") == "m"
