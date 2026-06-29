from __future__ import annotations

import pytest

from application.dtos.chat_dtos import AgentEvent
from infrastructure.chat.models import ContextMetadata, QueryPlan
from infrastructure.chat.nodes.adaptive_synthesis import (
    AdaptiveSynthesisNode,
    _synthesis_reasoning_on,
)
from infrastructure.llm import reasoning_context


class _FakeLLM:
    async def complete(self, prompt, **kw):  # noqa: ANN001, ANN003, ARG002
        return "PLAN"

    async def stream_with_reasoning(self, prompt, **kw):  # noqa: ANN001, ANN003, ARG002
        yield ("reasoning", "thinking hard")
        yield ("content", "the answer")


class _FakePrompts:
    async def render_prompt(self, name, **kw):  # noqa: ANN001, ANN003, ARG002
        return "SYS"


def _plan():
    return QueryPlan(
        query_type="factual", reformulated_query="q",
        search_strategy="hierarchical", summary="s",
    )


def _ctx():
    return ContextMetadata(
        total_sources=1, high_relevance_count=1, avg_relevance_score=0.9,
        unique_artifacts=1, has_summaries=False,
    )


@pytest.mark.asyncio
async def test_reasoning_emitted_as_event() -> None:
    node = AdaptiveSynthesisNode(_FakeLLM(), _FakePrompts())
    items = [pair async for pair in node.run("q", _plan(), "sources", _ctx(), [])]

    reasoning = [p for k, p in items if k == "event"
                 and isinstance(p, AgentEvent) and p.type == "reasoning_token"]
    assert reasoning and reasoning[0].delta == "thinking hard"

    tokens = "".join(p for k, p in items if k == "token")
    assert "the answer" in tokens


def test_reasoning_token_is_valid_event_type() -> None:
    ev = AgentEvent(type="reasoning_token", delta="x")
    assert ev.delta == "x"


def test_synthesis_reasoning_on_reads_lane_override() -> None:
    tok = reasoning_context.set_reasoning_override({"synthesis": "medium"})
    try:
        assert _synthesis_reasoning_on() is True
    finally:
        reasoning_context.reset_reasoning_override(tok)

    tok = reasoning_context.set_reasoning_override({"synthesis": "off"})
    try:
        assert _synthesis_reasoning_on() is False
    finally:
        reasoning_context.reset_reasoning_override(tok)


def _planning_events(items: list) -> list:
    return [
        p for k, p in items
        if k == "event" and isinstance(p, AgentEvent) and p.thinking_label == "Answer Planning"
    ]


@pytest.mark.asyncio
async def test_answer_planning_skipped_when_reasoning_on() -> None:
    # Model reasoning already plans the answer → no separate planning call/block.
    node = AdaptiveSynthesisNode(_FakeLLM(), _FakePrompts())
    tok = reasoning_context.set_reasoning_override({"synthesis": "high"})
    try:
        items = [pair async for pair in node.run("q", _plan(), "sources", _ctx(), [])]
    finally:
        reasoning_context.reset_reasoning_override(tok)
    assert not _planning_events(items)


@pytest.mark.asyncio
async def test_answer_planning_emitted_when_reasoning_off() -> None:
    node = AdaptiveSynthesisNode(_FakeLLM(), _FakePrompts())
    tok = reasoning_context.set_reasoning_override({"synthesis": "off"})
    try:
        items = [pair async for pair in node.run("q", _plan(), "sources", _ctx(), [])]
    finally:
        reasoning_context.reset_reasoning_override(tok)
    assert _planning_events(items)
