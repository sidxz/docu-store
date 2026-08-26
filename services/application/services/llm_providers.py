"""BYO-LLM provider presets — the single place model defaults live.

``provider``/``base_url`` are what the resolver hands ``build_chat_model``:
``openrouter`` is OpenAI-compatible, so it maps to ``openai`` plus a fixed base
URL. ``model`` serves the batch + NER lanes, ``chat_model`` the chat lanes
(Phase 2 ``effective_spec``). Users may override both; these are the prefill.
"""

from __future__ import annotations

from dataclasses import dataclass

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class ProviderPreset:
    provider: str  # what build_chat_model / langextract see
    base_url: str | None
    model: str
    chat_model: str


PRESETS: dict[str, ProviderPreset] = {
    "openrouter": ProviderPreset(
        "openai", OPENROUTER_BASE_URL, "openai/gpt-5-mini", "openai/gpt-5"
    ),
    "openai": ProviderPreset("openai", None, "gpt-5-mini", "gpt-5"),
    "gemini": ProviderPreset("gemini", None, "gemini-2.5-flash", "gemini-2.5-pro"),
}
