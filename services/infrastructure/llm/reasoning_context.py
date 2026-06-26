"""Request-scoped per-lane reasoning override (set by the chat use case, read by
the LLM adapters). Per-task isolation via contextvars — safe across concurrent
requests sharing singleton adapters.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_reasoning_override: ContextVar[dict[str, str] | None] = ContextVar(
    "reasoning_override", default=None,
)


def set_reasoning_override(levels: dict[str, str] | None) -> Token:
    return _reasoning_override.set(levels)


def reset_reasoning_override(token: Token) -> None:
    _reasoning_override.reset(token)


def get_lane_override(lane: str | None) -> str | None:
    """The override level for ``lane``, or None (no override / unknown lane / batch)."""
    if lane is None:
        return None
    levels = _reasoning_override.get()
    return levels.get(lane) if levels else None
