"""The retrieval loop for Literature mode.

Europe PMC ranks a result set against the fielded query the model wrote. Nothing
in that ordering knows what the user actually asked, and context assembly cuts on
whatever order it is handed — so without this step the answer is built from
whichever papers happened to arrive first.

A subclass rather than a branch inside AgenticRetrievalNode: the internal-docs
pipeline already scores its own results during retrieval, and it must not acquire
a literature-shaped code path it never executes.
"""

from __future__ import annotations

import asyncio
import math
from typing import TYPE_CHECKING, Any

import structlog

from application.ports.reranker import RerankDocument
from infrastructure.chat.nodes.agentic_retrieval import AgenticRetrievalNode

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from application.ports.reranker import Reranker
    from infrastructure.chat.models import RetrievalResult

log = structlog.get_logger(__name__)

# Abstract characters handed to the cross-encoder. Matches the internal search
# path, and ms-marco truncates at 512 tokens anyway.
_RERANK_TEXT_CHARS = 2000
# Above this many candidates the CPU cross-encoder costs more than the precision
# it buys. The tail beyond this cap is kept, in Europe PMC order, below every
# scored result rather than dropped.
_MAX_RERANK_CANDIDATES = 200
# What a hit scores when there is no relevance signal at all — RERANKER_ENABLED
# off, or no query to score against. It must not be the tool's placeholder 1.0:
# that puts every abstract in the HIGH tier and pushes avg_relevance_score above
# chat_verification_relevance_threshold (0.4), which switches the grounding check
# off silently, on a surface whose answers then look maximally grounded. Below
# that threshold so verification runs, above _MEDIUM (0.05) so abstracts are not
# cut to 200 characters.
_UNSCORED = 0.3


def _sigmoid(x: float) -> float:
    """Squash a cross-encoder logit into (0, 1).

    ms-marco-MiniLM returns raw logits — measured range on real abstracts is about
    -7.2 to +1.3 — while every threshold downstream is expressed as a probability.
    Clamped because math.exp overflows around 710.
    """
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


class LiteratureRetrievalNode(AgenticRetrievalNode):
    """Agentic retrieval, plus a relevance score the assembly stage can rank on."""

    def __init__(
        self,
        *args: Any,
        reranker: Reranker | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._reranker = reranker

    async def run(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> AsyncGenerator[tuple[str, Any], None]:
        question = kwargs.get("question") or (args[3] if len(args) > 3 else "")
        plan = kwargs.get("plan") or (args[0] if args else None)
        # ms-marco-MiniLM is trained on natural-language queries. This surface
        # also takes raw Europe PMC field syntax straight from the user (e.g.
        # `TITLE_ABS:"InhA" AND PUB_YEAR:[2024 TO 2026]`), and that scores near
        # zero against every abstract -- measured live: top score 0.025, 0
        # results reach the HIGH tier, vs. 0.788 / 5 HIGH for a natural-language
        # question. The planner's reformulation is natural language regardless
        # of what the user typed, so prefer it and fall back to the raw
        # question only when it is missing.
        reformulated = (getattr(plan, "reformulated_query", "") or "").strip()
        rerank_query = reformulated or question
        async for kind, payload in super().run(*args, **kwargs):
            if kind == "results" and payload:
                payload = await self._rescore(rerank_query, payload)
            yield kind, payload

    async def _rescore(
        self,
        question: str,
        results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        """Score every hit against the user's question, best first."""
        if not results:
            return results
        if not self._reranker or not question:
            log.warning(
                "literature.rerank.unavailable",
                reranker=bool(self._reranker),
                results=len(results),
            )
            return [r.model_copy(update={"rerank_score": _UNSCORED}) for r in results]

        candidates = results[:_MAX_RERANK_CANDIDATES]
        docs = [
            RerankDocument(
                id=str(i),
                text=(r.artifact_title or "") + "\n" + r.expanded_text[:_RERANK_TEXT_CHARS],
            )
            for i, r in enumerate(candidates)
        ]

        scored = await asyncio.to_thread(self._reranker.rerank, question, docs)
        by_index = {int(s.id): _sigmoid(s.score) for s in scored}

        ranked = [
            r.model_copy(update={"rerank_score": by_index[i]})
            for i, r in enumerate(candidates)
            if i in by_index
        ]

        # The tail beyond the cap is preserved but never outranks a scored hit.
        # 0.0 is strictly below every sigmoid output (clamped minimum ~9.4e-14),
        # and an explicit sentinel is required: leaving rerank_score None would
        # make ContextAssemblyNode._score fall back to similarity_score, which is
        # a hardcoded 1.0 for literature and would rank the tail first.
        ranked.extend(
            r.model_copy(update={"rerank_score": 0.0})
            for r in results[_MAX_RERANK_CANDIDATES:]
        )
        ranked.sort(key=lambda r: r.rerank_score or 0.0, reverse=True)

        log.info(
            "literature.reranked",
            candidates=len(candidates),
            unscored_tail=len(results) - len(candidates),
            top_score=f"{ranked[0].rerank_score:.3f}" if ranked else None,
            bottom_score=f"{ranked[-1].rerank_score:.3f}" if ranked else None,
        )
        return ranked
