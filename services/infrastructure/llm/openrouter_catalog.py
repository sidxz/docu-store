"""What OpenRouter publishes about its models, so we need not ask them.

Every model on OpenRouter's public (unauthenticated) catalog carries a
``supported_parameters`` list. For the one capability entity extraction cannot
run without — strict ``json_schema`` structured output — that turns a spent LLM
call into a lookup, and it catches a case a live probe cannot: OpenRouter *drops*
unsupported parameters rather than erroring, so a model listing ``response_format``
but not ``structured_outputs`` answers the probe happily in prose instead of
refusing it. 86 of 387 catalogued models lacked ``structured_outputs`` when this
was written, 36 of them while still listing ``response_format``.

The answer is trustworthy in one direction only. ``supported_parameters`` is the
union across every upstream provider a model id can route to, so an absent
capability is a reliable no while a present one is not a guarantee. The listing is
not always complete either — a handful of models declare ``structured_outputs``
and omit ``response_format`` — which is why only an *absent* ``structured_outputs``
is acted on. This narrows what the live probe has to discover; it does not
replace it.

For OpenAI and Gemini the reading inverts. OpenRouter resells both, and those
entries route to one upstream — the vendor's own API, the same endpoint we would
be calling — so there a listed capability is as good as a live answer while an
absent one says nothing (OpenRouter lists what it resells, not what Google
ships). That makes the same fetch a current list of what those two offer, which
is what the settings form suggests instead of a table of model names that would
be stale by its second release.
"""

from __future__ import annotations

import re
import time

import structlog

logger = structlog.get_logger()

MODELS_URL = "https://openrouter.ai/api/v1/models"
STRUCTURED_OUTPUT_PARAM = "structured_outputs"

# provider id → (catalog vendor, the prefix its chat models share). OpenRouter
# resells both, so its catalog doubles as a live list of what they currently ship.
_VENDORS = {"openai": ("openai", "openai/"), "gemini": ("google", "google/gemini")}

_SUGGESTION_LIMIT = 12
# Variants and non-text models an ingestion pipeline has no use for. Their slugs
# are also where OpenRouter's naming drifts furthest from the vendor's own ids,
# which is the other reason a suggestion list is better off without them.
_NOT_A_SUGGESTION = re.compile(
    r"[:@]|image|audio|realtime|tts|whisper|embed|search|codex|latest|customtools"
)

_TIMEOUT_SECONDS = 5.0
_CACHE_TTL_SECONDS = 6 * 60 * 60

# ponytail: no fetch lock, so a cold cache under concurrent saves fetches more
# than once. Harmless and self-correcting; add one if settings writes ever burst.
_cache: dict[str, frozenset[str]] | None = None
_cached_at = 0.0


async def supports_structured_outputs(model_id: str) -> bool | None:
    """Whether ``model_id`` accepts strict ``json_schema``.

    ``None`` when the catalog cannot answer — the model is not listed, or the
    fetch failed. Callers must treat that as "ask the provider instead", never as
    a refusal: an unreachable third-party catalog is not evidence about a model.
    """
    catalog = await _catalog()
    if catalog is None:
        return None
    params = catalog.get(model_id)
    if params is None:
        return None
    return STRUCTURED_OUTPUT_PARAM in params


def catalog_id(provider: str, model: str) -> str | None:
    """The catalog's id for a model called ``model`` on ``provider``'s own API.

    None for a provider OpenRouter does not resell.
    """
    vendor = _VENDORS.get(provider)
    return f"{vendor[0]}/{model}" if vendor else None


async def suggested_models(provider: str) -> tuple[str, ...]:
    """Models to offer for ``provider``, newest first, named as its own API names them.

    A hint for the settings form, not a contract: the field stays free text, and
    the save gate remains the thing that actually decides. Empty for a provider
    OpenRouter does not resell (its own catalog is left to the user, who picked
    the advanced option) and empty whenever the catalog is unreachable.
    """
    vendor = _VENDORS.get(provider)
    catalog = await _catalog()
    if vendor is None or catalog is None:
        return ()
    _, prefix = vendor
    suggestions = []
    for model_id, params in catalog.items():  # API order, newest first
        if not model_id.startswith(prefix) or _NOT_A_SUGGESTION.search(model_id):
            continue
        if not {STRUCTURED_OUTPUT_PARAM, "tools"} <= params:
            continue
        suggestions.append(model_id.split("/", 1)[1])
        if len(suggestions) == _SUGGESTION_LIMIT:
            break
    return tuple(suggestions)


async def _catalog() -> dict[str, frozenset[str]] | None:
    global _cache, _cached_at
    if _cache is not None and time.monotonic() - _cached_at < _CACHE_TTL_SECONDS:
        return _cache
    fetched = await _fetch_catalog()
    if fetched is None:
        return _cache  # a stale answer beats no answer; None on a cold cache
    _cache, _cached_at = fetched, time.monotonic()
    return _cache


async def _fetch_catalog() -> dict[str, frozenset[str]] | None:
    """``{model_id: supported_parameters}``, or None if OpenRouter is unreachable."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(MODELS_URL)
            response.raise_for_status()
            data = response.json()["data"]
    except Exception:
        logger.warning("openrouter_catalog_unavailable", exc_info=True)
        return None
    return {
        model["id"]: frozenset(model.get("supported_parameters") or [])
        for model in data
        if model.get("id")
    }
