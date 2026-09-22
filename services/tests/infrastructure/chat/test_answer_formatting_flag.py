"""CHAT_ENABLE_ANSWER_FORMATTING=false must still deliver the answer.

Clients build the assistant message from ``token`` deltas alone, so skipping the
rewrite without emitting the draft yields an empty answer -- silently, since every
other event still looks healthy.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from infrastructure.chat.models import ContextMetadata, GroundingResult, QueryPlan
from infrastructure.chat.thinking_agent import ThinkingAgent

DRAFT = "Compound 8d shows CC50 12 uM against HepG2 [1]."


class _Planning:
    async def run(self, message, history, **kw):
        return QueryPlan(
            reformulated_query=message, query_type="factual",
            search_strategy="hybrid", summary="",
        ), ""


class _Retrieval:
    async def run(self, *a, **kw):
        yield "results", []


class _Assembly:
    def run(self, results):
        return [], "", ContextMetadata(
            total_sources=0, high_relevance_count=0, avg_relevance_score=0.0,
            unique_artifacts=0, has_summaries=False,
        )


class _Synthesis:
    async def run(self, *a, **kw):
        yield "token", DRAFT


class _Verification:
    async def run(self, *a, **kw):
        return GroundingResult(
            is_grounded=True, confidence=1.0, verification_summary="ok", llm_verified=True,
        ), ""


class _Formatting:
    """Records whether the rewrite was reached, and mangles the text if it was."""

    def __init__(self) -> None:
        self.called = False

    async def run(self, message, draft):
        self.called = True
        yield "REWRITTEN"


class _TagDict:
    async def suggest_tags(self, *a, **kw):
        return []


def _agent(formatting: _Formatting) -> ThinkingAgent:
    return ThinkingAgent(
        query_planning=_Planning(),
        agentic_retrieval=_Retrieval(),
        context_assembly=_Assembly(),
        adaptive_synthesis=_Synthesis(),
        inline_verification=_Verification(),
        answer_formatting=formatting,
        tag_dictionary=_TagDict(),
    )


async def _answer(agent: ThinkingAgent) -> tuple[str, list]:
    text, events = "", []
    async for ev in agent.run("how potent is 8d?", [], workspace_id=uuid4()):
        events.append(ev)
        if ev.type == "token" and ev.delta:
            text += ev.delta
    return text, events


def _formatting_step(events: list) -> object:
    return next(
        e for e in events
        if e.type == "step_completed" and e.step == "formatting"
    )


@pytest.mark.asyncio
async def test_disabled_streams_the_draft_and_skips_the_rewrite(monkeypatch) -> None:
    from infrastructure import config

    monkeypatch.setattr(config.settings, "chat_enable_answer_formatting", False)
    fmt = _Formatting()

    text, events = await _answer(_agent(fmt))

    assert not fmt.called, "the rewrite must not run when the flag is off"
    assert text == DRAFT, "the draft must reach the client as token deltas"
    assert _formatting_step(events).output == "Formatting disabled"


@pytest.mark.asyncio
async def test_enabled_is_unchanged(monkeypatch) -> None:
    from infrastructure import config

    monkeypatch.setattr(config.settings, "chat_enable_answer_formatting", True)
    fmt = _Formatting()

    text, events = await _answer(_agent(fmt))

    assert fmt.called
    assert text == "REWRITTEN"
    assert _formatting_step(events).output.startswith("Formatted (")
