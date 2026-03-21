"""Step 1: Analyze the user's question to determine search strategy."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog

from infrastructure.chat.models import QuestionAnalysis
from infrastructure.config import settings

if TYPE_CHECKING:
    from application.dtos.chat_dtos import ChatMessageDTO
    from application.ports.llm_client import LLMClientPort
    from application.ports.prompt_repository import PromptRepositoryPort

log = structlog.get_logger(__name__)


class QuestionAnalysisNode:
    """Classify the query, extract entities, and pick a search strategy."""

    def __init__(
        self,
        llm_client: LLMClientPort,
        prompt_repository: PromptRepositoryPort,
    ) -> None:
        self._llm = llm_client
        self._prompts = prompt_repository

    async def run(
        self,
        question: str,
        conversation_history: list[ChatMessageDTO],
    ) -> QuestionAnalysis:
        conversation_context = _build_conversation_context(conversation_history)

        prompt = await self._prompts.render_prompt(
            "chat_question_analysis",
            question=question,
            conversation_context=conversation_context or "No prior conversation.",
        )

        if settings.chat_debug:
            log.info(
                "chat.debug.analysis.prompt",
                prompt_len=len(prompt),
                prompt_preview=prompt[:500],
                history_len=len(conversation_history),
                context_preview=conversation_context[:300] if conversation_context else "(none)",
            )

        log.debug("chat.analysis.start", question_len=len(question))

        try:
            raw = await self._llm.complete(prompt)

            if settings.chat_debug:
                log.info("chat.debug.analysis.raw_response", raw_len=len(raw), raw=raw[:1000])

            # Strip markdown fences if the LLM wrapped the JSON
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

            data = json.loads(cleaned)
            analysis = QuestionAnalysis(**data)
            log.info(
                "chat.analysis.done",
                query_type=analysis.query_type,
                strategy=analysis.search_strategy,
                entities=analysis.entities[:5],
                reformulated_query=analysis.reformulated_query[:200],
            )
            return analysis

        except (json.JSONDecodeError, Exception) as exc:
            log.warning("chat.analysis.fallback", error=str(exc), raw_preview=raw[:500] if "raw" in dir() else "(no response)")
            return QuestionAnalysis(
                query_type="factual",
                reformulated_query=question,
                entities=[],
                smiles_detected=[],
                search_strategy="hierarchical",
                summary=question[:200],
            )


def _build_conversation_context(history: list[ChatMessageDTO]) -> str:
    """Build a concise context string from recent conversation history."""
    if not history:
        return ""
    lines = []
    for msg in history[-6:]:  # Last 3 pairs
        role = "User" if msg.role == "user" else "Assistant"
        text = msg.content[:300]
        lines.append(f"{role}: {text}")
    return "\n".join(lines)
