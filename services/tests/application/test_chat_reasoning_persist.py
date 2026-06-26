from __future__ import annotations

from application.dtos.chat_dtos import AgentTraceDTO


def test_agent_trace_carries_reasoning_content() -> None:
    trace = AgentTraceDTO(reasoning_content="model thoughts")
    assert trace.reasoning_content == "model thoughts"
    # Round-trips through the persisted dict shape used by the chat repo.
    assert AgentTraceDTO(**trace.model_dump()).reasoning_content == "model thoughts"


def test_agent_trace_reasoning_defaults_none() -> None:
    # Old persisted docs lack the field; it must default cleanly.
    assert AgentTraceDTO().reasoning_content is None
    assert AgentTraceDTO(steps=[], thinking_blocks=[]).reasoning_content is None
