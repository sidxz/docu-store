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

    from application.dtos.chat_dtos import SourceCitationDTO
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
        skip_unfiltered_seed: bool = False,
        previous_citations: list[SourceCitationDTO] | None = None,
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

        # ── 0. Seed carried-forward citations from previous grounded turn ──
        carried_forward_count = 0
        if previous_citations:
            carried_forward_count = accumulator.seed_carried_forward(previous_citations)
            log.info(
                "chat.agentic_retrieval.carried_forward",
                citation_count=len(previous_citations),
                seeded=carried_forward_count,
                artifact_titles=[c.artifact_title for c in previous_citations[:5]],
            )

        # Detect explicit citation references like [2] in the question
        import re

        explicit_refs = {int(m) for m in re.findall(r"\[(\d{1,2})\]", question)}
        if explicit_refs and previous_citations:
            log.info(
                "chat.agentic_retrieval.explicit_refs_detected",
                refs=sorted(explicit_refs),
            )
            for c in previous_citations:
                if c.citation_index in explicit_refs and c.page_id:
                    page_results, _, _ = await self._tools.execute(
                        "get_page_content",
                        {"page_id": str(c.page_id)},
                        workspace_id,
                        allowed_artifact_ids,
                    )
                    if page_results:
                        accumulator.add_results(page_results, f"explicit_ref_{c.citation_index}")
                        log.info(
                            "chat.agentic_retrieval.explicit_ref_loaded",
                            citation_index=c.citation_index,
                            page_id=str(c.page_id),
                        )

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

        filtered_results, filtered_summary, _ = await self._tools.execute(
            "search_documents",
            seed_args_filtered,
            workspace_id,
            allowed_artifact_ids,
        )
        accumulator.add_results(filtered_results, plan.reformulated_query)

        # Second search: same query, NO filters — catches pages missed by NER
        # In factual mode (skip_unfiltered_seed=True), always skip the unfiltered
        # seed. Unfiltered search only runs on verification failure retry.
        seed_summary = filtered_summary
        new_from_unfiltered = 0
        did_skip_unfiltered = False
        if has_filters:
            if skip_unfiltered_seed:
                did_skip_unfiltered = True
                log.info(
                    "chat.agentic_retrieval.skip_unfiltered",
                    filtered_count=len(filtered_results),
                )
            else:
                unfiltered_args = {"query": plan.reformulated_query, "limit": 10}
                unfiltered_results, unfiltered_summary, _ = await self._tools.execute(
                    "search_documents",
                    unfiltered_args,
                    workspace_id,
                    allowed_artifact_ids,
                )
                new_from_unfiltered = accumulator.add_results(
                    unfiltered_results,
                    f"{plan.reformulated_query}_unfiltered",
                )
                if new_from_unfiltered > 0:
                    seed_summary += (
                        f"\n\nBroader search (no entity filters) added "
                        f"{new_from_unfiltered} more results:\n{unfiltered_summary}"
                    )

        # ── 1b. Deterministic bioactivity pre-fetch for compound NER ──
        bioactivity_count = 0
        compound_entities = [f for f in plan.ner_entity_filters if f.entity_type == "compound_name"]
        target_entities = [
            f for f in plan.ner_entity_filters if f.entity_type in ("target", "gene_name")
        ]
        if compound_entities and "search_structured_bioactivity" in self._tools._tools:
            for compound in compound_entities:
                bio_args: dict[str, str] = {"compound_name": compound.entity_text}
                if target_entities:
                    bio_args["target_name"] = target_entities[0].entity_text
                bio_results, bio_summary, _ = await self._tools.execute(
                    "search_structured_bioactivity",
                    bio_args,
                    workspace_id,
                    allowed_artifact_ids,
                )
                new_bio = accumulator.add_results(
                    bio_results,
                    f"bioactivity:{compound.entity_text}",
                )
                bioactivity_count += new_bio
                if bio_summary:
                    seed_summary += f"\n\nStructured bioactivity data:\n{bio_summary}"

                # Always log bioactivity fetch (key diagnostic)
                log.info(
                    "chat.agentic_retrieval.bioactivity_prefetch",
                    compound=compound.entity_text,
                    target=bio_args.get("target_name"),
                    results=len(bio_results),
                    new=new_bio,
                    summary=bio_summary[:300] if bio_summary else "",
                )

                # Emit SSE event so frontend shows what was found
                yield (
                    "event",
                    AgentEvent(
                        type="step_completed",
                        step="retrieval",
                        status="completed",
                        output=(
                            f"Bioactivity pre-fetch: {compound.entity_text}"
                            + (
                                f" × {bio_args.get('target_name')}"
                                if bio_args.get("target_name")
                                else ""
                            )
                            + f" → {len(bio_results)} results ({new_bio} new)"
                            + (f": {bio_summary[:200]}" if bio_summary and new_bio > 0 else "")
                        ),
                    ),
                )

        # ── 1c. SMILES-resolved page pre-fetch ──
        smiles_page_count = 0
        if plan.smiles_context and plan.smiles_context.resolved:
            for compound in plan.smiles_context.resolved:
                for page_id in compound.page_ids[:3]:  # cap per compound
                    page_results, _, _ = await self._tools.execute(
                        "get_page_content",
                        {"page_id": str(page_id)},
                        workspace_id,
                        allowed_artifact_ids,
                    )
                    if page_results:
                        new_smiles = accumulator.add_results(
                            page_results,
                            f"smiles:{compound.canonical_smiles}",
                        )
                        smiles_page_count += new_smiles

                log.info(
                    "chat.agentic_retrieval.smiles_page_prefetch",
                    canonical_smiles=compound.canonical_smiles,
                    extracted_ids=compound.extracted_ids,
                    pages_fetched=min(len(compound.page_ids), 3),
                    new_results=smiles_page_count,
                )

            if smiles_page_count > 0:
                yield (
                    "event",
                    AgentEvent(
                        type="step_completed",
                        step="retrieval",
                        status="completed",
                        output=(
                            f"SMILES resolution: {len(plan.smiles_context.resolved)} compounds "
                            f"({', '.join(c.canonical_smiles for c in plan.smiles_context.resolved)}) "
                            f"→ {smiles_page_count} new pages"
                        ),
                    ),
                )

        # ── 1d. Compound structure pre-fetch for NER compound mentions ──
        structure_count = 0
        if compound_entities and "search_compound_structure" in self._tools._tools:
            for compound in compound_entities[:3]:  # cap to 3 compounds
                struct_results, struct_summary, struct_events = await self._tools.execute(
                    "search_compound_structure",
                    {"compound_name": compound.entity_text},
                    workspace_id,
                    allowed_artifact_ids,
                )
                for evt in struct_events:
                    yield ("event", evt)
                new_struct = accumulator.add_results(
                    struct_results,
                    f"structure:{compound.entity_text}",
                )
                structure_count += new_struct
                if struct_summary:
                    seed_summary += f"\n\nCompound structure data:\n{struct_summary}"
                log.info(
                    "chat.agentic_retrieval.structure_prefetch",
                    compound=compound.entity_text,
                    results=len(struct_results),
                    new=new_struct,
                    events=len(struct_events),
                )

        total_seed = (
            len(filtered_results)
            + new_from_unfiltered
            + bioactivity_count
            + smiles_page_count
            + structure_count
        )
        output_parts = [f"Initial search: {len(filtered_results)} filtered"]
        if has_filters and not did_skip_unfiltered:
            output_parts.append(f" + {new_from_unfiltered} unfiltered")
        elif did_skip_unfiltered:
            output_parts.append(" (unfiltered skipped — factual mode)")
        if bioactivity_count > 0:
            output_parts.append(f" + {bioactivity_count} bioactivity")
        if smiles_page_count > 0:
            output_parts.append(f" + {smiles_page_count} SMILES pages")
        if structure_count > 0:
            output_parts.append(f" + {structure_count} structures")
        output_parts.append(f" = {total_seed} results")
        yield (
            "event",
            AgentEvent(
                type="step_completed",
                step="retrieval",
                status="completed",
                output="".join(output_parts),
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

        entities = ", ".join(f"{f.entity_text} ({f.entity_type})" for f in plan.ner_entity_filters)
        if plan.author_mentions:
            entities += (", " if entities else "") + ", ".join(plan.author_mentions)

        # Build SMILES resolution briefing for the retrieval LLM
        smiles_briefing = ""
        if plan.smiles_context and plan.smiles_context.resolved:
            briefing_lines = ["## SMILES Resolution"]
            for compound in plan.smiles_context.resolved:
                if compound.extracted_ids:
                    names = ", ".join(compound.extracted_ids)
                    briefing_lines.append(
                        f"- SMILES `{compound.canonical_smiles}` = compound **{names}**. "
                        f"Search using '{compound.extracted_ids[0]}', NOT the raw SMILES.",
                    )
            if plan.smiles_context.unresolved:
                briefing_lines.append(
                    f"- Unresolved SMILES (no match in database): "
                    f"{', '.join(plan.smiles_context.unresolved)}",
                )
            briefing_lines.append(
                "\nIMPORTANT: Always search using compound names/IDs, never raw SMILES strings. "
                "SMILES notation is not useful for text-based document search.",
            )
            smiles_briefing = "\n".join(briefing_lines)

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
            conversation_context=smiles_briefing,
        )

        carried_note = ""
        if carried_forward_count > 0:
            carried_note = (
                f"\n\nNote: {carried_forward_count} sources were carried forward from "
                "the previous turn. They are already in the accumulator."
            )

        smiles_note = ""
        if plan.smiles_context and plan.smiles_context.resolved:
            mappings = [
                f"{c.canonical_smiles} = {c.extracted_ids[0]}"
                for c in plan.smiles_context.resolved
                if c.extracted_ids
            ]
            if mappings:
                smiles_note = (
                    f"\n\nSMILES mapping: {'; '.join(mappings)}. "
                    "Search using compound names, not SMILES strings."
                )

        messages: list[dict] = [
            {
                "role": "user",
                "content": (
                    f"I need to answer: {question}\n\n"
                    f"Here are the initial search results:\n{seed_summary}\n\n"
                    f"{accumulator.summary_for_model()}{carried_note}{smiles_note}\n\n"
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
                if response.content:
                    yield (
                        "event",
                        AgentEvent(
                            type="step_completed",
                            step="retrieval",
                            status="completed",
                            output=f"Model finished retrieval ({accumulator.result_count} sources)",
                            thinking_content=response.content[:2000],
                            thinking_label=f"Retrieval Reasoning (iteration {iterations + 1})",
                        ),
                    )
                if _debug:
                    log.info(
                        "chat.debug.agentic_retrieval.model_done",
                        iteration=iterations,
                        content_preview=response.content[:200] if response.content else "",
                    )
                break

            # Process tool calls — emit model reasoning once per LLM response
            iteration_thought = response.content[:2000] if response.content else None
            thought_emitted = False

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
                            thinking_content=iteration_thought,
                            thinking_label=f"Retrieval Complete (iteration {iterations + 1})",
                        ),
                    )
                    # Break out of both loops
                    iterations = max_iterations  # Force outer loop exit
                    break

                # In factual mode, force-inject NER filters so the LLM
                # can't bypass entity scoping.
                tool_args = tc.tool_args
                if skip_unfiltered_seed:
                    if tc.tool_name in ("search_documents", "search_summaries"):
                        if entity_types and "entity_types" not in tool_args:
                            tool_args = {**tool_args, "entity_types": entity_types}
                        if tags and "tags" not in tool_args:
                            tool_args = {**tool_args, "tags": tags}
                    elif tc.tool_name == "search_structured_bioactivity":
                        compound_tags = [
                            f.entity_text
                            for f in plan.ner_entity_filters
                            if f.entity_type == "compound_name"
                        ]
                        if compound_tags and "compound_name" not in tool_args:
                            tool_args = {**tool_args, "compound_name": compound_tags[0]}

                if tool_args is not tc.tool_args:
                    log.info(
                        "chat.agentic_retrieval.force_injected",
                        tool=tc.tool_name,
                        original_args=tc.tool_args,
                        injected_args=tool_args,
                    )

                # Execute the tool
                tool_results, tool_summary, tool_events = await self._tools.execute(
                    tc.tool_name,
                    tool_args,
                    workspace_id,
                    allowed_artifact_ids,
                )
                for evt in tool_events:
                    yield ("event", evt)
                new_count = accumulator.add_results(
                    tool_results,
                    str(tc.tool_args.get("query", "")),
                )

                # Attach model reasoning to the first tool call event only
                tc_thinking = iteration_thought if not thought_emitted else None
                thought_emitted = True

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
                        thinking_content=tc_thinking,
                        thinking_label=f"Search Iteration {iterations + 1}"
                        if tc_thinking
                        else None,
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
                    messages.append(
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": tc.tool_call_id or f"call_{iterations}_{tc.tool_name}",
                                    "name": tc.tool_name,
                                    "args": tc.tool_args,
                                },
                            ],
                        },
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "content": tool_summary,
                            "tool_call_id": tc.tool_call_id or f"call_{iterations}_{tc.tool_name}",
                        },
                    )
                else:
                    # ReAct style: assistant thought, then observation
                    messages.append(
                        {
                            "role": "assistant",
                            "content": (
                                f"Thought: Searching for more information.\n"
                                f"Action: {tc.tool_name}\n"
                                f"Action Input: {tc.tool_args}"
                            ),
                        },
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "content": tool_summary,
                        },
                    )

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
