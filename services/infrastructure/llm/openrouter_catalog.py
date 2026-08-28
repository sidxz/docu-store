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
"""

from __future__ import annotations

import time

import structlog

logger = structlog.get_logger()

MODELS_URL = "https://openrouter.ai/api/v1/models"
STRUCTURED_OUTPUT_PARAM = "structured_outputs"

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
