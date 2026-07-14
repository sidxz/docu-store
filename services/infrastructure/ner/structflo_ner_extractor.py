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

import structlog

from application.ports.ner_extractor import NEREntity, NERExtractorPort

logger = structlog.get_logger()

# Entity types the fast extractor is specifically tuned for.
# Its gazetteer coverage for these classes is reliable and deterministic.
FAST_TARGET_TYPES: frozenset[str] = frozenset(
    {"accession_number", "gene_name", "screening_method", "target"},
)

# Providers langextract can route for NER. Anything else (anthropic, azure)
# → dictionary-only NER, since langextract has no provider for them.
LANGEXTRACT_PROVIDERS: frozenset[str] = frozenset({"ollama", "openai", "gemini"})


class StructfloNERExtractor(NERExtractorPort):
    """Runs fast + LLM NER and merges results.

    Args:
        model_id:  Model name (e.g. "gemma3:27b", "gpt-4o")
        provider:  langextract provider ("ollama"/"openai"/"gemini"). Providers
            outside that set degrade to dictionary-only NER.
        api_key:   API key for cloud providers (None for Ollama).
        model_url: Ollama base URL; ignored for cloud providers.

    """

    def __init__(
        self,
        model_id: str,
        provider: str = "ollama",
        api_key: str | None = None,
        model_url: str | None = None,
        max_char_buffer: int = 5000,
    ) -> None:
        from structflo.ner import TB
        from structflo.ner.fast import FastNERExtractor

        self._fast_extractor = FastNERExtractor(fuzzy_threshold=0)
        self._tb_profile = TB

        if provider in LANGEXTRACT_PROVIDERS:
            import langextract.providers as lx_providers
            from structflo.ner import NERExtractor

            # langextract 1.1.1: the explicit-provider factory path skips
            # load_builtins_once(), so a fresh process has an empty registry and
            # resolve_provider("ollama") raises InferenceConfigError — every LLM
            # extract silently degrades to dictionary-only. Register builtins
            # here until structflo-ner does it itself at construction.
            lx_providers.load_builtins_once()

            self._llm_extractor = NERExtractor(
                model_id=model_id,
                provider=provider,
                api_key=api_key,
                model_url=model_url if provider == "ollama" else None,
                profile=TB,
                langextract_kwargs={"max_char_buffer": max_char_buffer},
            )
        else:
            # langextract can't route this provider — run dictionary-only NER
            # rather than crashing on the first extract() call.
            self._llm_extractor = None
            logger.warning("structflo_ner_llm_provider_unsupported", provider=provider)

        logger.info(
            "structflo_ner_extractor_initialized",
            model_id=model_id,
            provider=provider,
            llm_enabled=self._llm_extractor is not None,
            max_char_buffer=max_char_buffer,
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
        if self._llm_extractor is None:
            return []
        try:
            result = await asyncio.to_thread(
                self._llm_extractor.extract,
                text,
                self._tb_profile,
            )
            entities = result.all_entities()  # type: ignore[union-attr]
            return [
                NEREntity(
                    text=e.text,
                    entity_type=e.entity_type,
                    confidence=getattr(e, "confidence", None),
                    attributes=dict(e.attributes) if e.attributes else {},
                )
                for e in entities
            ]
        except Exception:
            logger.exception("structflo_ner_llm_extractor_failed")
            return []

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
