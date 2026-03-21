"""Stage 1 (Thinking Mode): Query Planning & Decomposition.

Three parallel tracks: NER extraction + GLiNER2 author detection + LLM planning.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import structlog

from infrastructure.chat.models import (
    NEREntityFilter,
    QUERY_FILTER_ENTITY_TYPES,
    QueryPlan,
)
from infrastructure.config import settings

if TYPE_CHECKING:
    from application.dtos.chat_dtos import ChatMessageDTO
    from application.ports.llm_client import LLMClientPort
    from application.ports.ner_extractor import NERExtractorPort
    from application.ports.prompt_repository import PromptRepositoryPort
    from application.ports.structured_extractor import StructuredExtractorPort

log = structlog.get_logger(__name__)

# GLiNER2 schema for author/person extraction
_AUTHOR_SCHEMA = [
    "author_name::person::Author or person name mentioned in the text",
]


class QueryPlanningNode:
    """Classify the query, decompose sub-queries, extract NER entities + authors."""

    def __init__(
        self,
        llm_client: LLMClientPort,
        prompt_repository: PromptRepositoryPort,
        ner_extractor: NERExtractorPort,
        structured_extractor: StructuredExtractorPort,
    ) -> None:
        self._llm = llm_client
        self._prompts = prompt_repository
        self._ner = ner_extractor
        self._structured_extractor = structured_extractor

    async def run(
        self,
        question: str,
        conversation_history: list[ChatMessageDTO],
    ) -> QueryPlan:
        conversation_context = _build_conversation_context(conversation_history)
        _debug = settings.chat_debug

        if _debug:
            log.info(
                "chat.debug.planning.start",
                question_len=len(question),
                history_len=len(conversation_history),
            )

        # Run all 3 extractors in parallel
        ner_task = self._run_ner(question)
        author_task = self._run_author_detection(question)
        llm_task = self._run_llm_planning(question, conversation_context)

        ner_filters, author_mentions, llm_plan = await asyncio.gather(
            ner_task, author_task, llm_task, return_exceptions=True,
        )

        # Handle individual failures gracefully
        if isinstance(ner_filters, BaseException):
            log.warning("chat.planning.ner_failed", error=str(ner_filters))
            ner_filters = []
        if isinstance(author_mentions, BaseException):
            log.warning("chat.planning.author_failed", error=str(author_mentions))
            author_mentions = []
        if isinstance(llm_plan, BaseException):
            log.warning("chat.planning.llm_failed", error=str(llm_plan))
            llm_plan = _default_llm_plan(question)

        # Merge into QueryPlan
        plan = llm_plan.model_copy(
            update={
                "ner_entity_filters": ner_filters,
                "author_mentions": author_mentions,
            },
        )

        if _debug:
            log.info(
                "chat.debug.planning.done",
                query_type=plan.query_type,
                strategy=plan.search_strategy,
                confidence=plan.confidence,
                sub_queries=plan.sub_queries,
                ner_filters=[(f.entity_text, f.entity_type) for f in plan.ner_entity_filters],
                author_mentions=plan.author_mentions,
                hyde=plan.hyde_hypothesis is not None,
            )

        return plan

    async def _run_ner(self, question: str) -> list[NEREntityFilter]:
        """Extract entities via StructfloNER, filter to whitelist."""
        entities = await self._ner.extract(question)

        filters = []
        for ent in entities:
            if ent.entity_type in QUERY_FILTER_ENTITY_TYPES:
                filters.append(
                    NEREntityFilter(entity_text=ent.text, entity_type=ent.entity_type),
                )

        log.info(
            "chat.planning.ner_done",
            total_entities=len(entities),
            filtered=len(filters),
            types=[f.entity_type for f in filters],
        )
        return filters

    async def _run_author_detection(self, question: str) -> list[str]:
        """Extract author/person names via GLiNER2."""
        fields = await self._structured_extractor.extract(
            question, _AUTHOR_SCHEMA, threshold=0.4,
        )
        authors = [f.value for f in fields if f.name == "author_name" and f.value.strip()]
        log.info("chat.planning.authors_done", count=len(authors), authors=authors)
        return authors

    async def _run_llm_planning(
        self,
        question: str,
        conversation_context: str,
    ) -> QueryPlan:
        """LLM call for query classification, sub-queries, HyDE, confidence."""
        enable_sub = "ENABLED — decompose if multi-faceted" if settings.chat_enable_sub_queries else "DISABLED — leave empty"
        enable_hyde = "ENABLED — generate for exploratory queries" if settings.chat_enable_hyde else "DISABLED — set to null"

        prompt = await self._prompts.render_prompt(
            "chat_query_planning",
            question=question,
            conversation_context=conversation_context or "No prior conversation.",
            enable_sub_queries=enable_sub,
            enable_hyde=enable_hyde,
        )

        if settings.chat_debug:
            log.info("chat.debug.planning.llm_prompt", prompt_len=len(prompt), preview=prompt[:500])

        raw = await self._llm.complete(prompt)

        if settings.chat_debug:
            log.info("chat.debug.planning.llm_raw", raw_len=len(raw), raw=raw[:1000])

        # Strip markdown fences
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        data = json.loads(cleaned)

        # Clamp sub_queries to max 3
        if "sub_queries" in data and len(data["sub_queries"]) > 3:
            data["sub_queries"] = data["sub_queries"][:3]

        return QueryPlan(**data)


def _default_llm_plan(question: str) -> QueryPlan:
    """Fallback plan when LLM planning fails."""
    return QueryPlan(
        query_type="factual",
        reformulated_query=question,
        search_strategy="hierarchical",
        confidence=0.5,
        summary=question[:200],
    )


def _build_conversation_context(history: list[ChatMessageDTO]) -> str:
    if not history:
        return ""
    lines = []
    for msg in history[-6:]:
        role = "User" if msg.role == "user" else "Assistant"
        lines.append(f"{role}: {msg.content[:300]}")
    return "\n".join(lines)
