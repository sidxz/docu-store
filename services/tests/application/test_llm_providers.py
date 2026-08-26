"""Provider presets — the single place BYO model defaults live."""

from __future__ import annotations

from application.services.llm_providers import OPENROUTER_BASE_URL, PRESETS


def test_presets_cover_the_three_user_facing_providers() -> None:
    assert set(PRESETS) == {"openrouter", "openai", "gemini"}


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
