"""Single construction point for LangChain chat models across all providers.

Wraps LangChain's ``init_chat_model`` so every LLM adapter (text + tool-calling)
builds models the same way, and so cloud providers can be hard-disabled for
confidential deployments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from langchain.chat_models import init_chat_model

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

log = structlog.get_logger(__name__)

# Providers that run locally and are always allowed (no data leaves the host).
LOCAL_PROVIDERS = frozenset({"ollama"})

# Our config provider names → LangChain init_chat_model provider keys.
_PROVIDER_MAP = {
    "ollama": "ollama",
    "openai": "openai",
    "anthropic": "anthropic",
    "gemini": "google_genai",
}


def _reasoning_kwargs(provider: str, reasoning: str | None) -> dict[str, Any]:
    """Translate a normalized reasoning effort to provider-specific init kwargs.

    ``off``/None → no reasoning. The effort string is one of off|low|medium|high.
    """
    if not reasoning or reasoning == "off":
        return {}
    if provider == "ollama":
        return {"reasoning": True}
    if provider == "anthropic":
        # ponytail: fixed 2048-token budget; make it a config knob if a deploy
        # needs deeper thinking. Newer Opus may prefer {"type": "adaptive"}.
        return {"thinking": {"type": "enabled", "budget_tokens": 2048}}
    if provider == "openai":
        return {"reasoning_effort": reasoning}
    if provider == "gemini":
        return {"thinking_budget": 2048}
    return {}


def build_chat_model(
    *,
    provider: str,
    model_name: str,
    temperature: float,
    api_key: str | None = None,
    base_url: str | None = None,
    reasoning: str | None = None,
    allow_cloud: bool = True,
) -> BaseChatModel:
    """Construct a LangChain ``BaseChatModel`` for ``provider``.

    Raises:
        ValueError: unknown provider; a cloud provider while ``allow_cloud`` is
            False; or a missing API key for a cloud provider.
    """
    if provider not in _PROVIDER_MAP:
        msg = f"Unsupported LLM provider: {provider!r}. Valid: {sorted(_PROVIDER_MAP)}"
        raise ValueError(msg)

    is_local = provider in LOCAL_PROVIDERS
    if not is_local and not allow_cloud:
        msg = (
            f"Cloud LLM provider {provider!r} is disabled (ALLOW_CLOUD_LLM=false). "
            f"This deployment permits only local providers: {sorted(LOCAL_PROVIDERS)}."
        )
        raise ValueError(msg)

    kwargs: dict[str, Any] = {
        "model": model_name,
        "model_provider": _PROVIDER_MAP[provider],
        "temperature": temperature,
    }

    if is_local:
        kwargs["base_url"] = base_url or "http://localhost:11434"
    else:
        if not api_key:
            msg = f"API key required for cloud provider {provider!r}."
            raise ValueError(msg)
        # Gemini's LangChain integration expects google_api_key.
        kwargs["google_api_key" if provider == "gemini" else "api_key"] = api_key

    reasoning_kw = _reasoning_kwargs(provider, reasoning)
    if provider == "anthropic" and reasoning_kw:
        # Anthropic extended thinking requires temperature == 1.
        kwargs["temperature"] = 1.0
    kwargs.update(reasoning_kw)

    log.info(
        "llm.model_builder.build",
        provider=provider,
        model=model_name,
        reasoning=reasoning or "off",
        cloud=not is_local,
    )
    return init_chat_model(**kwargs)
