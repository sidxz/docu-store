"""Step 1 (Quick Mode): Analyze the user's question to determine search strategy.

Runs two parallel tracks:
  A) LLM analysis (query type, entities, strategy)
  B) Deterministic SMILES detection + resolution via compound vector store
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import structlog
from returns.result import Failure

from infrastructure.chat.models import QuestionAnalysis, ResolvedCompound, SmilesContext
from infrastructure.chat.utils import build_follow_up_context, strip_markdown_fences
from infrastructure.chemistry.smiles_detector import (
    detect_smiles,
    infer_smiles_search_mode,
)
from infrastructure.config import settings

if TYPE_CHECKING:
    from application.dtos.chat_dtos import ChatMessageDTO
    from application.ports.llm_client import LLMClientPort
    from application.ports.prompt_repository import PromptRepositoryPort
    from application.ports.smiles_validator import SmilesValidator
    from application.use_cases.smiles_search_use_cases import SearchSimilarCompoundsUseCase

log = structlog.get_logger(__name__)


class QuestionAnalysisNode:
    """Classify the query, extract entities, and pick a search strategy."""

    def __init__(
        self,
        llm_client: LLMClientPort,
        prompt_repository: PromptRepositoryPort,
        smiles_validator: SmilesValidator | None = None,
        smiles_search: SearchSimilarCompoundsUseCase | None = None,
    ) -> None:
        self._llm = llm_client
        self._prompts = prompt_repository
        self._smiles_validator = smiles_validator
        self._smiles_search = smiles_search

    async def run(
        self,
        question: str,
        conversation_history: list[ChatMessageDTO],
    ) -> QuestionAnalysis:
        conversation_context = build_follow_up_context(conversation_history)

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

        # Run LLM analysis and SMILES resolution in parallel
        llm_task = self._run_llm_analysis(prompt)
        smiles_task = self._run_smiles_resolution(question)

        llm_result, smiles_ctx = await asyncio.gather(
            llm_task,
            smiles_task,
            return_exceptions=True,
        )

        # Handle LLM failure
        if isinstance(llm_result, BaseException):
            log.warning("chat.analysis.fallback", error=str(llm_result))
            analysis = QuestionAnalysis(
                query_type="factual",
                reformulated_query=question,
                entities=[],
                smiles_detected=[],
                search_strategy="hierarchical",
                summary=question[:200],
            )
        else:
            analysis = llm_result

        # Handle SMILES failure gracefully
        if isinstance(smiles_ctx, BaseException):
            log.warning("chat.analysis.smiles_failed", error=str(smiles_ctx))
            smiles_ctx = None

        # Attach SMILES context and inject resolved compound names into entities
        if smiles_ctx and smiles_ctx.resolved:
            existing = {e.lower() for e in analysis.entities}
            injected = []
            for compound in smiles_ctx.resolved:
                for ext_id in compound.extracted_ids:
                    if ext_id.lower() not in existing:
                        injected.append(ext_id)
                        existing.add(ext_id.lower())
            if injected:
                analysis = analysis.model_copy(
                    update={
                        "entities": analysis.entities + injected,
                        "smiles_context": smiles_ctx,
                    },
                )
                log.info(
                    "chat.analysis.smiles_resolved",
                    detected=smiles_ctx.detected,
                    resolved=[c.canonical_smiles for c in smiles_ctx.resolved],
                    injected_entities=injected,
                    mode=smiles_ctx.mode,
                )
            else:
                analysis = analysis.model_copy(update={"smiles_context": smiles_ctx})
        elif smiles_ctx:
            analysis = analysis.model_copy(update={"smiles_context": smiles_ctx})

        # Rewrite reformulated_query to use compound names instead of raw SMILES
        if smiles_ctx and smiles_ctx.resolved:
            from infrastructure.chat.utils import replace_smiles_with_names

            rewritten = replace_smiles_with_names(analysis.reformulated_query, smiles_ctx)
            if rewritten != analysis.reformulated_query:
                log.info(
                    "chat.analysis.smiles_query_rewrite",
                    original=analysis.reformulated_query[:200],
                    rewritten=rewritten[:200],
                )
                analysis = analysis.model_copy(
                    update={"reformulated_query": rewritten},
                )

        return analysis

    async def _run_llm_analysis(self, prompt: str) -> QuestionAnalysis:
        """Run LLM question analysis."""
        raw = await self._llm.complete(prompt)

        if settings.chat_debug:
            log.info("chat.debug.analysis.raw_response", raw_len=len(raw), raw=raw[:1000])

        cleaned = strip_markdown_fences(raw)
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

    async def _run_smiles_resolution(self, question: str) -> SmilesContext | None:
        """Detect SMILES in the question and resolve against the compound store."""
        if not self._smiles_validator or not self._smiles_search or not settings.chat_smiles_resolution_enabled:
            return None

        from application.dtos.smiles_embedding_dtos import CompoundSearchRequest

        detected = detect_smiles(question, self._smiles_validator)
        if not detected:
            return None

        mode = infer_smiles_search_mode(question)
        threshold = (
            settings.chat_smiles_similar_threshold
            if mode == "similar"
            else settings.chat_smiles_exact_threshold
        )

        resolved: list[ResolvedCompound] = []
        unresolved: list[str] = []

        for det in detected:
            result = await self._smiles_search.execute(
                CompoundSearchRequest(
                    query_smiles=det.canonical,
                    limit=settings.chat_smiles_max_results,
                    score_threshold=threshold,
                ),
            )
            is_ok = not isinstance(result, Failure)
            if is_ok and result.unwrap().results:
                search_resp = result.unwrap()
                ext_ids: list[str] = []
                artifact_ids: list[str] = []
                page_ids: list[str] = []
                best_sim = 0.0
                seen_ids: set[str] = set()
                for r in search_resp.results:
                    if r.extracted_id and r.extracted_id not in seen_ids:
                        ext_ids.append(r.extracted_id)
                        seen_ids.add(r.extracted_id)
                    artifact_ids.append(str(r.artifact_id))
                    page_ids.append(str(r.page_id))
                    best_sim = max(best_sim, r.similarity_score)

                from uuid import UUID

                resolved.append(
                    ResolvedCompound(
                        canonical_smiles=det.canonical,
                        extracted_ids=ext_ids,
                        best_similarity=best_sim,
                        artifact_ids=[UUID(a) for a in dict.fromkeys(artifact_ids)],
                        page_ids=[UUID(p) for p in dict.fromkeys(page_ids)],
                    ),
                )
            else:
                unresolved.append(det.canonical)

        if not resolved and not unresolved:
            return None

        return SmilesContext(
            detected=[d.canonical for d in detected],
            detected_originals=[d.original for d in detected],
            resolved=resolved,
            unresolved=unresolved,
            mode=mode,
        )
