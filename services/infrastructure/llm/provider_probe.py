"""Live check of a UserLLMConfig: one tiny completion per distinct lane model,
plus a structured-output check for the NER lane.

Details are key-free by construction: ``LLMError`` messages come from
``infrastructure.llm.errors`` (no payload echo) and anything else is reported
by exception type only — SDK errors can embed request headers.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage

from domain.exceptions import LLMBadRequestError, LLMError
from infrastructure.llm.errors import translate_provider_errors
from infrastructure.llm.model_builder import LOCAL_PROVIDERS, build_chat_model

if TYPE_CHECKING:
    from application.ports.user_llm_config import UserLLMConfig

LaneResult = tuple[bool, str | None]

# One sentence with an unmistakable compound. Short enough to cost nothing,
# specific enough that an empty result means the model ignored the schema.
NER_PROBE_TEXT = "Gefitinib (ZD1839) inhibits EGFR with IC50 = 0.033 uM in NSCLC."


@dataclass(frozen=True)
class NerProbe:
    """Whether the ingestion model can do what NER needs, and how sure we are.

    ``refused`` marks a provider answering "no" to the request shape itself, which
    is the one verdict that blocks a save. A timeout, a 5xx, a rate limit or a bad
    key leaves the config writable, so a provider outage can never lock someone
    out of their own settings — including out of switching away from a model that
    does not work.
    """

    ok: bool
    detail: str | None = None
    refused: bool = False

    @property
    def lane(self) -> LaneResult:
        return self.ok, self.detail


async def probe_user_llm_config(cfg: UserLLMConfig, *, allow_cloud: bool) -> dict[str, LaneResult]:
    """``{"batch": …, "chat": …, "ner": …}`` — each distinct model probed once."""
    lanes = {"batch": cfg.model, "chat": cfg.chat_model or cfg.model}
    by_model: dict[str | None, LaneResult] = {}
    for model in lanes.values():
        if model not in by_model:
            by_model[model] = await _probe_model(cfg, model, allow_cloud=allow_cloud)
    results = {lane: by_model[model] for lane, model in lanes.items()}
    results["ner"] = (await probe_ner_support(cfg, allow_cloud=allow_cloud)).lane
    return results


def _ner_preflight(cfg: UserLLMConfig, *, allow_cloud: bool) -> NerProbe | None:
    """The answers we already know without spending a call. None → go ahead and probe."""
    from infrastructure.ner.structflo_ner_extractor import LANGEXTRACT_PROVIDERS

    if cfg.provider not in LANGEXTRACT_PROVIDERS:
        return NerProbe(
            ok=False,
            detail=f"Entity extraction cannot run on provider {cfg.provider!r}.",
            refused=True,
        )
    if cfg.provider not in LOCAL_PROVIDERS and not allow_cloud:
        return NerProbe(ok=False, detail="Cloud LLM providers are disabled on this deployment.")
    if not cfg.model:
        return NerProbe(ok=False, detail="No ingestion model configured.")
    return None


async def probe_ner_support(cfg: UserLLMConfig, *, allow_cloud: bool) -> NerProbe:
    """Run the real NER path on one sentence and report whether it works.

    The batch lane passing says nothing about this: a plain completion is exactly
    the request a model *without* strict structured output answers happily. NER
    goes through langextract with ``use_schema_constraints=True``, which sends
    ``response_format: {"type": "json_schema", "strict": true}`` — a request some
    OpenRouter routes reject outright. Probing with the small CHEMISTRY profile
    rather than the TB one the adapter uses keeps the prompt cheap: this is a
    capability check, not an extraction-quality check.
    """
    refusal = _ner_preflight(cfg, allow_cloud=allow_cloud)
    if refusal is not None:
        return refusal

    try:
        from structflo.ner import NERExtractor
        from structflo.ner.profiles import CHEMISTRY

        from infrastructure.ner.structflo_ner_extractor import BASE_URL_PROVIDERS

        extractor = NERExtractor(
            model_id=cfg.model,
            provider=cfg.provider,
            api_key=cfg.api_key,
            model_url=cfg.base_url if cfg.provider in BASE_URL_PROVIDERS else None,
            profile=CHEMISTRY,
        )
        with translate_provider_errors():
            result = await asyncio.to_thread(extractor.extract, NER_PROBE_TEXT)
    except LLMBadRequestError as exc:
        # A 4xx is not by itself proof the model cannot do structured output —
        # Gemini answers a malformed API key with a 400 too, and blocking a save
        # on that is the lockout this is supposed to avoid. It is a capability
        # refusal only if the same model, key and endpoint answer a plain
        # completion: then the schema is the only difference left standing.
        plain_ok, _ = await _probe_model(cfg, cfg.model, allow_cloud=allow_cloud)
        return NerProbe(ok=False, detail=str(exc), refused=plain_ok)
    except LLMError as exc:
        return NerProbe(ok=False, detail=str(exc))
    except Exception as exc:  # never echo SDK payloads
        return NerProbe(ok=False, detail=f"Unexpected {type(exc).__name__}")

    if not result.compounds:  # type: ignore[union-attr]
        # It answered, but ignored the schema. Report it, do not block the save:
        # one bad sentence is weaker evidence than an outright refusal.
        return NerProbe(
            ok=False,
            detail="Model returned no entities for a sentence that plainly contains one.",
        )
    return NerProbe(ok=True)


async def _probe_model(cfg: UserLLMConfig, model: str | None, *, allow_cloud: bool) -> LaneResult:
    if not model:
        return False, "No model configured."
    try:
        with translate_provider_errors():
            llm = build_chat_model(
                provider=cfg.provider,
                model_name=model,
                temperature=0.0,
                api_key=cfg.api_key,
                base_url=cfg.base_url,
                allow_cloud=allow_cloud,
            )
            await llm.ainvoke([HumanMessage(content="Reply with OK.")])
    except LLMError as exc:
        return False, str(exc)
    except Exception as exc:  # never echo SDK payloads
        return False, f"Unexpected {type(exc).__name__}"
    return True, None
