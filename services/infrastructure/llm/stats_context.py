"""Request-scoped Stats flag (set by the chat use case, read by ToolRegistry).

ToolRegistry is built once in DI, so a per-message flag cannot gate tool
registration directly, and threading a boolean through ChatAgentPort would touch
the port, the router and every agent -- note the router does not even forward
`mode` to the agent, it selects one. This is the same bridge `reasoning_context`
builds for the same reason, and per-task isolation via contextvars is what makes
it safe across concurrent turns sharing singletons.
"""

from __future__ import annotations

from collections.abc import Iterable
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

# What was drawn, not just how much: (panel, the facet subjects it plotted).
# A turn can run retrieval twice -- the grounding retry rebuilds the agent loop
# with fresh messages -- and the second pass replots the first pass's chart,
# usually minus a facet. Counting alone cannot see that; a signature can.
_panels_drawn: ContextVar[tuple[tuple[str, frozenset[str]], ...]] = ContextVar(
    "panels_drawn", default=(),
)


def _subjects(queries: Iterable[str]) -> frozenset[str]:
    return frozenset(" ".join(q.split()).lower() for q in queries)


def claim_panel_slot(panel: str, queries: Iterable[str]) -> bool:
    """Take one of this turn's panel slots. False when the budget is spent."""
    drawn = _panels_drawn.get()
    if len(drawn) >= MAX_PANELS_PER_TURN:
        return False
    _panels_drawn.set((*drawn, (panel, _subjects(queries))))
    return True


def panel_budget_spent() -> bool:
    """Whether the turn's budget is already exhausted, without claiming a slot.

    The budget counts panels drawn, not panels attempted: a caller that may
    still refuse after this check (no data, a source error) should peek here
    first, so a refusal costs zero Europe PMC requests and zero slots.
    """
    return len(_panels_drawn.get()) >= MAX_PANELS_PER_TURN


def panel_already_drawn(panel: str, queries: Iterable[str]) -> bool:
    """Same panel, no subject this turn has not already plotted.

    Subset rather than equality: the observed duplicate was a strict subset of
    the first pass's facets, so comparing signatures for equality would have
    let it through.
    """
    want = _subjects(queries)
    return any(p == panel and want <= drawn for p, drawn in _panels_drawn.get())


def reset_panel_budget() -> Token:
    """Start a turn with a full budget. Reset with :func:`reset_stats_enabled`'s twin."""
    return _panels_drawn.set(())


def restore_panel_budget(token: Token) -> None:
    _panels_drawn.reset(token)


# The queries this turn actually searched with. The chart must count the papers
# the cards came from; without a record of what was searched, a facet built out
# of a retrieved paper's title passes every other guard and silently charts a
# different population than the answer read.
#
# ``default=None`` rather than an empty list: a mutable default is one list
# shared by every turn that never called reset. Appending in place is also what
# makes it survive a context copy, which ``.set()`` on the panel counter does not.
_searched: ContextVar[list[str] | None] = ContextVar("searched_queries", default=None)


def reset_searched_queries() -> Token:
    return _searched.set([])


def restore_searched_queries(token: Token) -> None:
    _searched.reset(token)


def record_searched_query(query: str) -> None:
    """Note a query that produced cards. A no-op outside a Stats turn."""
    if (queries := _searched.get()) is not None:
        queries.append(query)


def searched_queries() -> list[str]:
    return list(_searched.get() or ())
