"""Stage 2 (Thinking Mode v2): Agentic Iterative Retrieval.

Replaces the fixed one-shot IntelligentRetrievalNode with a model-driven
iterative loop. The model gets search tools, decides what to search,
evaluates results, and searches again if needed.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Literal

import structlog

from application.dtos.chat_dtos import AgentEvent
from infrastructure.chat.models import QueryPlan, RetrievalResult
from infrastructure.chat.retrieval_accumulator import RetrievalAccumulator
from infrastructure.config import settings

if TYPE_CHECKING:
    from uuid import UUID

    from application.ports.prompt_repository import PromptRepositoryPort
    from application.ports.tool_calling_llm import ToolCallingLLMPort
    from infrastructure.chat.tools.retrieval_tools import ToolRegistry

log = structlog.get_logger(__name__)


class AgenticRetrievalNode:
    """Iterative tool-calling retrieval loop driven by the LLM."""

    def __init__(
        self,
        tool_llm: ToolCallingLLMPort,
        tool_registry: ToolRegistry,
        prompt_repository: PromptRepositoryPort,
    ) -> None:
        self._tool_llm = tool_llm
        self._tools = tool_registry
        self._prompts = prompt_repository

    async def run(
        self,
        plan: QueryPlan,
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
        question: str,
    ) -> AsyncGenerator[
        tuple[Literal["event", "results"], AgentEvent | list[RetrievalResult]],
        None,
    ]:
        """Run the agentic retrieval loop.

        Yields:
            ("event", AgentEvent) — step events for SSE streaming
            ("results", list[RetrievalResult]) — final accumulated results (last yield)
        """
        _debug = settings.chat_debug
        max_iterations = settings.chat_agent_max_iterations
        iteration_timeout = settings.chat_agent_iteration_timeout_s
        total_timeout = settings.chat_agent_total_timeout_s
        accumulator = RetrievalAccumulator()
        loop_start = time.monotonic()

        # ── 1. Auto-seed first search using the query plan ──
        entity_types = list({f.entity_type for f in plan.ner_entity_filters})
        # target and gene_name are interchangeable — if either is present, include both
        if {"target", "gene_name"} & set(entity_types):
            for t in ("target", "gene_name"):
                if t not in entity_types:
                    entity_types.append(t)
        entity_types = entity_types or None
        tags = [f.entity_text for f in plan.ner_entity_filters] + plan.author_mentions
        tags = tags or None

        has_filters = bool(entity_types or tags)

        seed_args_filtered = {"query": plan.reformulated_query, "limit": 10}
        if entity_types:
            seed_args_filtered["entity_types"] = entity_types
        if tags:
            seed_args_filtered["tags"] = tags

        filtered_results, filtered_summary = await self._tools.execute(
            "search_documents", seed_args_filtered, workspace_id, allowed_artifact_ids,
        )
        accumulator.add_results(filtered_results, plan.reformulated_query)

        # Second search: same query, NO filters — catches pages missed by NER
        seed_summary = filtered_summary
        new_from_unfiltered = 0
        if has_filters:
            unfiltered_args = {"query": plan.reformulated_query, "limit": 10}
            unfiltered_results, unfiltered_summary = await self._tools.execute(
                "search_documents", unfiltered_args, workspace_id, allowed_artifact_ids,
            )
            new_from_unfiltered = accumulator.add_results(
                unfiltered_results, f"{plan.reformulated_query}_unfiltered",
            )
            if new_from_unfiltered > 0:
                seed_summary += (
                    f"\n\nBroader search (no entity filters) added "
                    f"{new_from_unfiltered} more results:\n{unfiltered_summary}"
                )

        total_seed = len(filtered_results) + new_from_unfiltered
        yield (
            "event",
            AgentEvent(
                type="step_completed",
                step="retrieval",
                status="completed",
                output=(
                    f"Initial search: {len(filtered_results)} filtered"
                    + (f" + {new_from_unfiltered} unfiltered" if has_filters else "")
                    + f" = {total_seed} results"
                ),
            ),
        )

        if _debug:
            log.info(
                "chat.debug.agentic_retrieval.seed",
                filtered=len(filtered_results),
                unfiltered_new=new_from_unfiltered,
                total=total_seed,
                chars=accumulator.chars_used,
            )

        # ── 2. Build initial messages for the LLM ──
        plan_summary = (
            f"Type: {plan.query_type}. Strategy: {plan.search_strategy}. "
            f"Confidence: {plan.confidence:.0%}."
        )
        if plan.sub_queries:
            plan_summary += f" Sub-queries: {', '.join(plan.sub_queries)}"

        entities = ", ".join(
            f"{f.entity_text} ({f.entity_type})" for f in plan.ner_entity_filters
        )
        if plan.author_mentions:
            entities += (", " if entities else "") + ", ".join(plan.author_mentions)

        prompt_name = (
            "chat_agentic_retrieval"
            if self._tool_llm.supports_native_tools
            else "chat_agentic_retrieval_react"
        )

        system_prompt = await self._prompts.render_prompt(
            prompt_name,
            question=question,
            plan_summary=plan_summary,
            entities=entities or "None detected",
            conversation_context="",
        )

        messages: list[dict] = [
            {
                "role": "user",
                "content": (
                    f"I need to answer: {question}\n\n"
                    f"Here are the initial search results:\n{seed_summary}\n\n"
                    f"{accumulator.summary_for_model()}\n\n"
                    "Evaluate these results. If they are sufficient, call finish_retrieval. "
                    "Otherwise, search for additional information."
                ),
            },
        ]

        # ── 3. Iterative loop ──
        iterations = 0

        while iterations < max_iterations:
            # Check total timeout
            elapsed = time.monotonic() - loop_start
            if elapsed > total_timeout:
                log.info("chat.agentic_retrieval.total_timeout", elapsed_s=elapsed)
                yield (
                    "event",
                    AgentEvent(
                        type="step_completed",
                        step="retrieval",
                        status="completed",
                        output=f"Retrieval timeout after {iterations} iterations",
                    ),
                )
                break

            # Check capacity
            if accumulator.is_at_capacity():
                log.info("chat.agentic_retrieval.at_capacity", chars=accumulator.chars_used)
                yield (
                    "event",
                    AgentEvent(
                        type="step_completed",
                        step="retrieval",
                        status="completed",
                        output=f"Context budget reached ({accumulator.result_count} sources)",
                    ),
                )
                break

            # Call LLM with tools
            try:
                response = await asyncio.wait_for(
                    self._tool_llm.invoke_with_tools(
                        messages=messages,
                        tools=self._tools.definitions,
                        system_prompt=system_prompt,
                    ),
                    timeout=iteration_timeout,
                )
            except TimeoutError:
                log.warning("chat.agentic_retrieval.iteration_timeout", iteration=iterations)
                yield (
                    "event",
                    AgentEvent(
                        type="step_completed",
                        step="retrieval",
                        status="completed",
                        output=f"Iteration {iterations + 1} timed out",
                    ),
                )
                break
            except Exception as exc:
                log.warning("chat.agentic_retrieval.llm_error", error=str(exc))
                break

            # No tool calls → model is done
            if not response.tool_calls:
                if _debug:
                    log.info(
                        "chat.debug.agentic_retrieval.model_done",
                        iteration=iterations,
                        content_preview=response.content[:200] if response.content else "",
                    )
                break

            # Process tool calls
            for tc in response.tool_calls:
                if tc.tool_name == "finish_retrieval":
                    if _debug:
                        log.info("chat.debug.agentic_retrieval.finish", iteration=iterations)
                    yield (
                        "event",
                        AgentEvent(
                            type="step_completed",
                            step="retrieval",
                            status="completed",
                            output=f"Model finished retrieval ({accumulator.result_count} sources)",
                        ),
                    )
                    # Break out of both loops
                    iterations = max_iterations  # Force outer loop exit
                    break

                # Execute the tool
                tool_results, tool_summary = await self._tools.execute(
                    tc.tool_name, tc.tool_args, workspace_id, allowed_artifact_ids,
                )
                new_count = accumulator.add_results(tool_results, str(tc.tool_args.get("query", "")))

                yield (
                    "event",
                    AgentEvent(
                        type="step_completed",
                        step="retrieval",
                        status="completed",
                        output=(
                            f"Searched: {tc.tool_args.get('query', tc.tool_name)[:80]} "
                            f"→ {len(tool_results)} results ({new_count} new)"
                        ),
                    ),
                )

                if _debug:
                    log.info(
                        "chat.debug.agentic_retrieval.tool_call",
                        iteration=iterations,
                        tool=tc.tool_name,
                        args=tc.tool_args,
                        results=len(tool_results),
                        new=new_count,
                        total=accumulator.result_count,
                    )

                # Append tool call + result to messages for next iteration
                if self._tool_llm.supports_native_tools:
                    messages.append({
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "id": tc.tool_call_id or f"call_{iterations}_{tc.tool_name}",
                            "name": tc.tool_name,
                            "args": tc.tool_args,
                        }],
                    })
                    messages.append({
                        "role": "tool",
                        "content": tool_summary,
                        "tool_call_id": tc.tool_call_id or f"call_{iterations}_{tc.tool_name}",
                    })
                else:
                    # ReAct style: assistant thought, then observation
                    messages.append({
                        "role": "assistant",
                        "content": (
                            f"Thought: Searching for more information.\n"
                            f"Action: {tc.tool_name}\n"
                            f"Action Input: {tc.tool_args}"
                        ),
                    })
                    messages.append({
                        "role": "tool",
                        "content": tool_summary,
                    })

            iterations += 1

        # ── 4. Return accumulated results ──
        all_results = accumulator.get_all_results()
        elapsed_total = time.monotonic() - loop_start

        log.info(
            "chat.agentic_retrieval.done",
            iterations=iterations,
            total_results=len(all_results),
            elapsed_s=f"{elapsed_total:.1f}",
            chars_used=accumulator.chars_used,
        )

        yield ("results", all_results)
