"""Dual-mode NER adapter wrapping structflo-ner.

Strategy:
- FastNERExtractor  runs first — dictionary/fuzzy matching, sub-second, deterministic.
  Reliable for well-defined entity classes: accession_number, gene_name,
  screening_method, target.
- NERExtractor (LLM) runs second — full TB profile, catches everything FastNER
  can find and more (bioactivity values, mechanisms, diseases, compound names …).
- Results are merged: LLM entities take precedence; fast-only entities that the
  LLM missed are appended.  De-duplication key: (text.lower().strip(), entity_type).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from application.ports.ner_extractor import NEREntity, NERExtractorPort
from domain.exceptions import LLMNotConfiguredError
from infrastructure.llm.errors import translate_provider_errors

if TYPE_CHECKING:
    from structflo.ner import NERExtractor

logger = structlog.get_logger()

# Entity types the fast extractor is specifically tuned for.
# Its gazetteer coverage for these classes is reliable and deterministic.
# compound_name earns its place from structflo-ner 0.5.0, where registry and
# programme identifiers (CHEMBL…, SACC-3060, LGENI-9743) match by regex rather
# than by gazetteer — the LLM lane labels those inconsistently, half of them
# landing on accession_number, which QUERY_FILTER_ENTITY_TYPES then drops.
FAST_TARGET_TYPES: frozenset[str] = frozenset(
    {"accession_number", "compound_name", "gene_name", "screening_method", "target"},
)

# Providers langextract can route for NER. Anything else (anthropic, azure)
# → dictionary-only NER, since langextract has no provider for them.
LANGEXTRACT_PROVIDERS: frozenset[str] = frozenset({"ollama", "openai", "gemini"})

# Providers whose langextract model accepts a base URL (Gemini's does not).
BASE_URL_PROVIDERS: frozenset[str] = frozenset({"ollama", "openai"})


class StructfloNERExtractor(NERExtractorPort):
    """Runs fast + LLM NER and merges results.

    The LLM extractor is built per call from the effective config — the
    caller's ``UserLLMConfig`` (contextvar) overlaid on these constructor
    defaults — so the same adapter serves every user. Construction is cheap
    (structflo stores fields; langextract routing happens inside ``extract``).

    Args:
        model_id:  Model name (e.g. "gemma3:27b", "gpt-4o")
        provider:  langextract provider ("ollama"/"openai"/"gemini"). Providers
            outside that set degrade to dictionary-only NER.
        api_key:   API key for cloud providers (None for Ollama).
        model_url: Base URL for ollama/openai (OpenRouter); ignored for gemini.

    """

    def __init__(
        self,
        model_id: str,
        provider: str = "ollama",
        api_key: str | None = None,
        model_url: str | None = None,
        max_char_buffer: int = 5000,
    ) -> None:
        import langextract.providers as lx_providers
        from structflo.ner import TB
        from structflo.ner.fast import FastNERExtractor

        # langextract 1.1.1: the explicit-provider factory path skips
        # load_builtins_once(), so a fresh process has an empty registry and
        # resolve_provider("ollama") raises InferenceConfigError. Register
        # builtins here until structflo-ner does it itself at construction.
        lx_providers.load_builtins_once()

        self._fast_extractor = FastNERExtractor(fuzzy_threshold=0)
        self._tb_profile = TB
        self._model_id = model_id
        self._provider = provider
        self._api_key = api_key
        self._model_url = model_url
        self._max_char_buffer = max_char_buffer

        logger.info(
            "structflo_ner_extractor_initialized",
            model_id=model_id,
            provider=provider,
            llm_routable=provider in LANGEXTRACT_PROVIDERS,
            max_char_buffer=max_char_buffer,
        )

    def _llm_extractor(self) -> NERExtractor | None:
        """Structflo NERExtractor for the effective config; None when langextract can't route it.

        Raises:
            LLMNotConfiguredError: cloud provider with no key (fail closed).

        """
        from structflo.ner import NERExtractor

        from infrastructure.llm.llm_context import get_user_config

        cfg = get_user_config()
        if cfg is not None:
            provider, model_id = cfg.provider, cfg.model or self._model_id
            api_key, model_url = cfg.api_key, cfg.base_url
        else:
            provider, model_id = self._provider, self._model_id
            api_key, model_url = self._api_key, self._model_url

        if provider not in LANGEXTRACT_PROVIDERS:
            logger.warning("structflo_ner_llm_provider_unsupported", provider=provider)
            return None
        if provider != "ollama" and not api_key:
            msg = f"No API key for NER provider {provider!r} — add one in your LLM settings."
            raise LLMNotConfiguredError(msg)
        return NERExtractor(
            model_id=model_id,
            provider=provider,
            api_key=api_key,
            model_url=model_url if provider in BASE_URL_PROVIDERS else None,
            profile=self._tb_profile,
            langextract_kwargs={"max_char_buffer": self._max_char_buffer},
        )

    async def extract(self, text: str) -> list[NEREntity]:
        if not text or not text.strip():
            return []

        fast_entities, llm_entities = await asyncio.gather(
            self._run_fast(text),
            self._run_llm(text),
        )

        return self._merge(fast_entities, llm_entities)

    async def _run_fast(self, text: str) -> list[NEREntity]:
        try:
            result = await asyncio.to_thread(self._fast_extractor.extract, text)
            entities = result.all_entities()  # type: ignore[union-attr]
            # Keep only the entity types the fast extractor handles well
            return [
                NEREntity(
                    text=e.text,
                    entity_type=e.entity_type,
                    confidence=None,
                    attributes=dict(e.attributes) if e.attributes else {},
                )
                for e in entities
                if e.entity_type in FAST_TARGET_TYPES
            ]
        except Exception:
            logger.exception("structflo_ner_fast_extractor_failed")
            return []

    async def _run_llm(self, text: str) -> list[NEREntity]:
        """LLM NER. Failures propagate (typed where the provider tells us why) —
        an empty list here would be persisted as a finished extraction.
        """
        extractor = self._llm_extractor()
        if extractor is None:
            return []
        with translate_provider_errors():
            result = await asyncio.to_thread(extractor.extract, text, self._tb_profile)
        return [
            NEREntity(
                text=e.text,
                entity_type=e.entity_type,
                confidence=getattr(e, "confidence", None),
                attributes=dict(e.attributes) if e.attributes else {},
            )
            for e in result.all_entities()  # type: ignore[union-attr]
        ]

    @staticmethod
    def _merge(
        fast_entities: list[NEREntity],
        llm_entities: list[NEREntity],
    ) -> list[NEREntity]:
        """LLM results win on overlap; fast-only entities are appended."""
        seen: set[tuple[str, str]] = {(e.text.lower().strip(), e.entity_type) for e in llm_entities}
        merged = list(llm_entities)
        for e in fast_entities:
            key = (e.text.lower().strip(), e.entity_type)
            if key not in seen:
                merged.append(e)
                seen.add(key)
        return merged
