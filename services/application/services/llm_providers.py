"""BYO-LLM provider presets — the single place model defaults live.

``provider``/``base_url`` are what the resolver hands ``build_chat_model``:
``openrouter`` is OpenAI-compatible, so it maps to ``openai`` plus a fixed base
URL. ``model`` serves the batch + NER lanes, ``chat_model`` the chat lanes
(Phase 2 ``effective_spec``). Users may override both; these are the prefill,
unless ``models`` is set — then those are the only models a workspace may pick.
"""

from __future__ import annotations

from dataclasses import dataclass

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Texas A&M's TAMU AI Chat (Open WebUI); offered only when TAMU_AI_ENABLED=true.
TAMU_AI_BASE_URL = "https://chat-api.tamu.ai/openai"
TAMU_LUNA, TAMU_SOL = "protected.gpt-5.6-luna", "protected.gpt-5.6-sol"


@dataclass(frozen=True)
class ProviderPreset:
    provider: str  # what build_chat_model / langextract see
    base_url: str | None
    model: str
    chat_model: str
    models: tuple[str, ...] = ()


PRESETS: dict[str, ProviderPreset] = {
    "openrouter": ProviderPreset(
        "openai", OPENROUTER_BASE_URL, "openai/gpt-5-mini", "openai/gpt-5"
    ),
    "openai": ProviderPreset("openai", None, "gpt-5-mini", "gpt-5"),
    "gemini": ProviderPreset("gemini", None, "gemini-2.5-flash", "gemini-2.5-pro"),
    "tamu": ProviderPreset(
        "openai", TAMU_AI_BASE_URL, TAMU_LUNA, TAMU_LUNA, models=(TAMU_LUNA, TAMU_SOL)
    ),
}


_GATEWAYS = {OPENROUTER_BASE_URL: "OpenRouter", TAMU_AI_BASE_URL: "TAMU AI"}
_VENDORS = {
    "openai": "OpenAI",
    "gemini": "Gemini",
    "google_genai": "Gemini",
    "anthropic": "Anthropic",
    "ollama": "Ollama",
}


def served_by(provider: str | None, base_url: str | None, model: str) -> str:
    """``Provider / model`` as the UI shows it: the gateway when there is one, else
    the vendor. Just the model when nothing says who served it.
    """
    label = _GATEWAYS.get(base_url or "") or _VENDORS.get(provider or "", provider)
    return f"{label} / {model}" if label else model
