"""Request-scoped Stats flag (set by the chat use case, read by ToolRegistry).

ToolRegistry is built once in DI, so a per-message flag cannot gate tool
registration directly, and threading a boolean through ChatAgentPort would touch
the port, the router and every agent -- note the router does not even forward
`mode` to the agent, it selects one. This is the same bridge `reasoning_context`
builds for the same reason, and per-task isolation via contextvars is what makes
it safe across concurrent turns sharing singletons.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_stats_enabled: ContextVar[bool] = ContextVar("stats_enabled", default=False)


def set_stats_enabled(on: bool) -> Token:
    return _stats_enabled.set(on)


def reset_stats_enabled(token: Token) -> None:
    _stats_enabled.reset(token)


def stats_enabled() -> bool:
    """Whether this turn asked for chart panels. Off unless explicitly set."""
    return _stats_enabled.get()


# Two panels is a reading budget, not a technical one: a third chart on one
# answer does not get read. It lives here rather than on the tool because the
# tool is a singleton and this must reset every turn -- keying it on anything
# the tool can see (workspace, conversation) would exhaust the budget once and
# refuse for ever after.
MAX_PANELS_PER_TURN = 2

_panels_drawn: ContextVar[int] = ContextVar("panels_drawn", default=0)


def claim_panel_slot() -> bool:
    """Take one of this turn's panel slots. False when the budget is spent."""
    drawn = _panels_drawn.get()
    if drawn >= MAX_PANELS_PER_TURN:
        return False
    _panels_drawn.set(drawn + 1)
    return True


def reset_panel_budget() -> Token:
    """Start a turn with a full budget. Reset with :func:`reset_stats_enabled`'s twin."""
    return _panels_drawn.set(0)


def restore_panel_budget(token: Token) -> None:
    _panels_drawn.reset(token)
