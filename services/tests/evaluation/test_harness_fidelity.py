"""The harness must hand the agent what SendMessageUseCase hands it.

A benchmark run that silently drops conversation history or carried-forward
citations measures the harness, not the product.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from application.dtos.chat_dtos import AgentEvent, ChatMessageDTO, QueryContextDTO, SourceCitationDTO
from application.use_cases.chat_use_cases import carried_forward_citations
from evaluation.ablation_configs import ABLATION_CONFIGS
from evaluation.eval_harness import run_conversation
from evaluation.query_set import EvalQuery, FollowUpContext


def _assistant(content: str, *, grounded: bool, sources: list[SourceCitationDTO]) -> ChatMessageDTO:
    return ChatMessageDTO(
        conversation_id=uuid4(),
        message_id=uuid4(),
        role="assistant",
        content=content,
        sources=sources,
        query_context=QueryContextDTO(grounded=grounded),
        created_at=datetime.now(UTC),
    )


def _citation() -> SourceCitationDTO:
    return SourceCitationDTO(
        citation_index=1, artifact_id=uuid4(), page_id=uuid4(), text_excerpt="x",
    )


class _RecordingAgent:
    """Captures every (message, history, previous_citations) the harness sends."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[ChatMessageDTO], list | None]] = []

    async def run(self, message, conversation_history, workspace_id, **kwargs):
        self.calls.append((message, list(conversation_history), kwargs.get("previous_citations")))
        yield AgentEvent(type="grounding_result", grounding_is_grounded=True, grounding_confidence=1.0)
        yield AgentEvent(type="done", sources=[_citation()], duration_ms=1, total_tokens=0)


def test_carried_forward_picks_last_grounded_assistant() -> None:
    wanted = [_citation()]
    history = [
        _assistant("older", grounded=True, sources=[_citation()]),
        _assistant("newest grounded", grounded=True, sources=wanted),
        _assistant("ungrounded, must be skipped", grounded=False, sources=[_citation()]),
    ]
    assert carried_forward_citations(history) == wanted
    assert carried_forward_citations([]) is None


def test_follow_up_turn_receives_its_authored_prior_turn() -> None:
    follow_up = EvalQuery(
        query_id="DECK-PMC10290938-q6",
        query_text="And what does it need to get to ninety percent?",
        query_type="follow_up",
        follow_up=FollowUpContext(
            turn_index=1,
            prior_queries=["How potent is BMS906024 itself against the parasite?"],
        ),
    )
    agent = _RecordingAgent()
    graded = asyncio.run(
        run_conversation(agent, [follow_up], uuid4(), "thinking", ABLATION_CONFIGS[0]),
    )

    # The prior turn ran, but only the authored query is graded and reported.
    assert [q.query_id for q, _ in graded] == ["DECK-PMC10290938-q6"]
    assert [msg for msg, _, _ in agent.calls] == [
        "How potent is BMS906024 itself against the parasite?",
        "And what does it need to get to ninety percent?",
    ]

    # The graded turn saw the prior exchange, and its grounded citations.
    _, history, previous_citations = agent.calls[1]
    assert [m.role for m in history] == ["user", "assistant"]
    assert history[0].content == "How potent is BMS906024 itself against the parasite?"
    assert previous_citations, "carried-forward citations were dropped"
