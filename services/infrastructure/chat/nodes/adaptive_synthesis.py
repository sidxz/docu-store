"""Stage 4 (Thinking Mode): Adaptive Answer Synthesis.

Selects query-type-specific system prompts, runs a lightweight
think-then-answer planning step, then streams the final answer.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Literal

import structlog

from application.dtos.chat_dtos import AgentEvent
from infrastructure.chat.utils import build_conversation_context
from infrastructure.config import settings

if TYPE_CHECKING:
    from application.dtos.chat_dtos import ChatMessageDTO
    from application.ports.llm_client import LLMClientPort
    from application.ports.prompt_repository import PromptRepositoryPort
    from infrastructure.chat.models import ContextMetadata, QueryPlan

log = structlog.get_logger(__name__)

# Appended to the context notes when the plan is flagged `aggregate`.
#
# Retrieval is not the whole story for these. Measured on the benchmark, 16
# questions had EVERY gold slide in the assembled context and still answered
# wrongly, and 11 of the 14 multi-slide cases cited fewer sources than the
# answer's population spans -- one had 8 gold slides in front of it and cited 1.
#
# It is a context note rather than a system prompt on purpose. Swapping the
# system prompt would take the citation discipline and the don't-guess rules with
# it, and those hold the abstain questions at 96%.
#
# Every sentence is answering something specific that fights it:
#   1. `chat_answer_synthesis_v2` instr. 9 ("Mentioning the same entity is NOT
#      enough") is a per-sentence relevance test, and it is what disqualifies rows
#      2..N of an enumeration. Naming the enumeration as the answer meets that test
#      on its own terms; asserting the question is "about a set" does not.
#   2. the measured failure: 11 of 14 multi-slide cases cited fewer sources than
#      the population spans.
#   3. result first, because `chat_system_factual` rule 2 demands it and
#      `chat_answer_formatting` reorders to the front anyway -- asking for
#      rows-then-total buys a conflict and loses it one stage later.
#   4. the comparability clause exists for MISCLASSIFIED lookups. Without it,
#      "every matching row" licenses pooling values across assays and units before
#      taking a minimum, which turns a correct single-table answer into a wrong
#      cross-table one that still carries a valid citation.
#   5. `_clip` deliberately marks a cut with "..." so the model can tell rows were
#      elided (see its docstring). A count is exactly where that matters.
#   6. the decline clause. "If a source has no matching row, leave it out" was the
#      first draft and it is not enough: it governs one non-matching source, never
#      the case where NOTHING matches. Abstain questions are disproportionately
#      aggregate-SHAPED ("how many X meet Y" where Y is simply unreported), so this
#      hint reaches them above the classifier's base error rate, and without this
#      sentence it hands them a template for a confident wrong number.
_SCAN_HINT = (
    "Here the enumeration is the answer: each matching row directly answers the "
    "question, so listing them is not unrelated information. The set usually spans "
    "several pages of the same document — stopping at the first page that matches "
    "undercounts. State the result in the first sentence, then list each row you "
    "counted with its citation. Count only rows measured the same way; never pool "
    "values across different assays or units. If a source is cut off (shown by "
    "'...'), the rows past the cut are not visible — say what you counted rather "
    "than presenting it as complete. If no source states the criterion, say the "
    "documents do not report it and give no number."
)

# Map query_type → system prompt key
_SYSTEM_PROMPT_MAP = {
    "factual": "chat_system_factual",
    "comparative": "chat_system_comparative",
    "exploratory": "chat_system_exploratory",
    "compound": "chat_system_compound",
    "follow_up": "chat_system_followup",
}


def _synthesis_reasoning_on() -> bool:
    """Whether model reasoning is enabled for the synthesis lane this request.

    Mirrors how the synthesis LLM client resolves its level (per-request
    override → CHAT_SYNTHESIS_REASONING → CHAT_LLM_REASONING). When on, the
    model's own chain-of-thought already plans the answer, so the separate
    planning call is skipped as redundant cost + a duplicate trace block.
    """
    from infrastructure.llm.reasoning_context import get_lane_override

    level = (
        get_lane_override("synthesis")
        or settings.chat_synthesis_reasoning
        or settings.chat_llm_reasoning
    )
    return bool(level) and level != "off"


class AdaptiveSynthesisNode:
    """Generate a grounded answer with query-type-specific prompting."""

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
        plan: QueryPlan,
        sources_text: str,
        context_meta: ContextMetadata,
        conversation_history: list[ChatMessageDTO],
        images_b64: list[str] | None = None,
    ) -> AsyncGenerator[tuple[Literal["token", "event"], str | AgentEvent], None]:
        """Stream answer tokens with adaptive prompting.

        Yields tagged tuples: ("event", AgentEvent) for intermediate thinking
        content, ("token", str) for answer tokens.
        """
        _debug = settings.chat_debug
        conversation_context = build_conversation_context(conversation_history, max_chars=500)

        # Select query-type-specific system prompt
        system_key = _SYSTEM_PROMPT_MAP.get(plan.query_type, "chat_system_factual")
        try:
            system_prompt = await self._prompts.render_prompt(system_key)
        except Exception:
            log.warning(
                "chat.adaptive_synthesis.system_prompt_fallback",
                attempted=system_key,
            )
            system_prompt = await self._prompts.render_prompt(
                "chat_system",
                workspace_context="",
            )

        # Build context hints from metadata
        context_hints = self._build_context_hints(context_meta, plan)
        if images_b64:
            context_hints += (
                f" {len(images_b64)} page images are attached for visual context."
                " Reference figures, charts, or diagrams visible in the images when relevant."
            )

        # Think-then-answer planning (small non-streaming call). Skipped when
        # model reasoning is on for the synthesis lane — the model's own
        # chain-of-thought (shown in the Reasoning panel) already plans the
        # answer, so a separate planning call would be redundant cost and a
        # duplicate "Answer Planning" block in the Process trace.
        if _synthesis_reasoning_on():
            # This lands in "Your answer plan (follow this closely)" -- the only
            # slot in the prompt carrying an explicit follow-this directive, and
            # it sits AFTER the context notes. "Map each source to the part of the
            # question it answers" is one-source-one-fact framing: for an
            # aggregate it restates the exact failure being fixed (8 gold slides
            # in context, 1 cited) with more authority than the hint that is
            # trying to prevent it. So the plan has to agree with the hint here,
            # or the hint argues with the prompt and loses.
            answer_plan = (
                (
                    "Enumerate every matching row across all the sources, cite each "
                    "one, then state the result — or say the documents do not report "
                    "it, if none of them state the criterion."
                )
                if plan.aggregate
                else (
                    "Reason step by step: map each source to the part of the question "
                    "it answers, then write the grounded answer."
                )
            )
        else:
            answer_plan = await self._plan_answer(
                question,
                plan,
                sources_text,
                context_hints,
            )

            if _debug:
                log.info(
                    "chat.debug.adaptive_synthesis.plan",
                    system_key=system_key,
                    context_hints=context_hints,
                    answer_plan_len=len(answer_plan),
                    answer_plan_preview=answer_plan[:300],
                )

            # Emit the answer plan as thinking content for the agent trace
            yield (
                "event",
                AgentEvent(
                    type="step_completed",
                    step="synthesis",
                    status="started",
                    output="Answer plan generated",
                    thinking_content=answer_plan,
                    thinking_label="Answer Planning",
                ),
            )

        # Build synthesis prompt
        user_prompt = await self._prompts.render_prompt(
            "chat_answer_synthesis_v2",
            question=question,
            sources=sources_text,
            conversation_context=conversation_context or "No prior conversation.",
            analysis_summary=plan.summary,
            answer_plan=answer_plan,
            context_hints=context_hints,
        )

        if _debug:
            log.info(
                "chat.debug.adaptive_synthesis.prompt",
                system_len=len(system_prompt),
                user_prompt_len=len(user_prompt),
            )

        token_count = 0
        async for kind, text in self._llm.stream_with_reasoning(
            user_prompt,
            system_prompt=system_prompt,
            images_b64=images_b64,
        ):
            if kind == "reasoning":
                yield ("event", AgentEvent(type="reasoning_token", delta=text))
            else:
                token_count += 1
                yield ("token", text)

        if _debug:
            log.info("chat.debug.adaptive_synthesis.done", tokens=token_count)

    async def _plan_answer(
        self,
        question: str,
        plan: QueryPlan,
        sources_text: str,
        context_hints: str,
    ) -> str:
        """Small non-streaming LLM call to plan the answer structure."""
        try:
            prompt = await self._prompts.render_prompt(
                "chat_answer_plan",
                question=question,
                query_type=plan.query_type,
                sources_preview=sources_text[:3000],
                context_hints=context_hints,
            )
            raw = await self._llm.complete(prompt)
            return raw.strip()[:500]  # Cap planning output
        except Exception as exc:
            log.warning("chat.adaptive_synthesis.plan_failed", error=str(exc))
            return "Answer the question directly using the provided sources."

    def _build_context_hints(
        self,
        meta: ContextMetadata,
        plan: QueryPlan,
    ) -> str:
        """Build context-aware hints for the synthesis prompt."""
        hints = []

        if meta.unique_artifacts == 1:
            hints.append("All sources come from a single document.")
        elif meta.unique_artifacts > 5:
            hints.append(
                f"Sources span {meta.unique_artifacts} different documents — synthesize across them.",
            )

        if meta.avg_relevance_score < 0.4:
            hints.append(
                "Sources may have limited relevance — be conservative and acknowledge gaps.",
            )

        if meta.has_summaries:
            hints.append(
                "Some sources are document summaries. Use summaries for context, cite chunks for factual claims.",
            )

        if meta.high_relevance_count == 0:
            hints.append("No highly relevant sources found. Be explicit about uncertainty.")

        if plan.sub_queries:
            hints.append(
                f"The question was decomposed into {len(plan.sub_queries)} sub-queries. Address each aspect.",
            )

        # Last, not first, for two reasons. The notes above it are the
        # conservatism guards ("be conservative and acknowledge gaps", "be
        # explicit about uncertainty"), and framing THOSE with "enumerate and
        # state a result" is backwards for exactly the population that must not
        # break. Last also puts it nearest the instructions that follow.
        #
        # `total_sources` gates it: with an empty context the note would open with
        # a counting frame and nothing to count, which is the shape of a
        # fabricated answer. `sources_text` is literally "No relevant sources
        # found." there, so nothing is lost by staying quiet.
        if plan.aggregate and meta.total_sources:
            hints.append(_SCAN_HINT)

        return " ".join(hints) if hints else "Standard context — proceed normally."
