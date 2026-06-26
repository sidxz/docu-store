from __future__ import annotations

import pytest

from infrastructure.llm.reasoning_context import (
    get_lane_override,
    reset_reasoning_override,
    set_reasoning_override,
)


def test_lane_override_basics() -> None:
    assert get_lane_override("synthesis") is None  # no override
    assert get_lane_override(None) is None
    tok = set_reasoning_override({"synthesis": "high"})
    try:
        assert get_lane_override("synthesis") == "high"
        assert get_lane_override("retrieval") is None  # lane absent
        assert get_lane_override(None) is None  # batch
    finally:
        reset_reasoning_override(tok)
    assert get_lane_override("synthesis") is None  # reset


@pytest.mark.asyncio
async def test_propagates_through_nested_async_generators() -> None:
    # Mimic: use_case (async gen, sets override) -> agent.run (async gen)
    # -> awaited adapter read. Proves the contextvar reaches the deep read.
    seen: list[str | None] = []

    async def adapter_call() -> None:
        seen.append(get_lane_override("synthesis"))

    async def agent_run():
        await adapter_call()
        yield "event"

    async def use_case():
        tok = set_reasoning_override({"synthesis": "high"})
        try:
            async for ev in agent_run():
                yield ev
        finally:
            reset_reasoning_override(tok)

    async for _ in use_case():
        pass

    assert seen == ["high"], (
        "ContextVar did not propagate through the async-generator pipeline. "
        "FALL BACK to explicit threading (see plan contingency)."
    )
