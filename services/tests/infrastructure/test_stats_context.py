"""The Stats flag is per-message; ToolRegistry is a DI singleton.

A contextvar is how this codebase already bridges that gap for `reasoning`, and
the reason it must be a contextvar rather than a module global is the third test
here: two concurrent turns must not see each other's flag.
"""

from __future__ import annotations

import asyncio

import pytest

from infrastructure.llm.stats_context import (
    claim_panel_slot,
    reset_panel_budget,
    reset_stats_enabled,
    restore_panel_budget,
    set_stats_enabled,
    stats_enabled,
)


def test_stats_is_off_when_nothing_set_it():
    assert stats_enabled() is False


def test_set_and_reset_restore_the_previous_value():
    token = set_stats_enabled(True)
    assert stats_enabled() is True
    reset_stats_enabled(token)
    assert stats_enabled() is False


def test_the_panel_budget_allows_exactly_two_then_refuses():
    token = reset_panel_budget()
    try:
        assert claim_panel_slot() is True
        assert claim_panel_slot() is True
        assert claim_panel_slot() is False
    finally:
        restore_panel_budget(token)


async def test_the_panel_budget_is_per_turn_not_per_process():
    # Keyed on the turn's context, so a second turn starts full. Keying it on
    # anything the singleton tool can see would spend the budget once for good.
    async def turn() -> list[bool]:
        token = reset_panel_budget()
        try:
            return [claim_panel_slot(), claim_panel_slot(), claim_panel_slot()]
        finally:
            restore_panel_budget(token)

    first, second = await asyncio.gather(turn(), turn())
    assert first == [True, True, False]
    assert second == [True, True, False]


async def test_two_concurrent_turns_do_not_see_each_others_flag():
    seen: dict[str, bool] = {}

    async def turn(name: str, on: bool, delay: float) -> None:
        token = set_stats_enabled(on)
        await asyncio.sleep(delay)
        seen[name] = stats_enabled()
        reset_stats_enabled(token)

    await asyncio.gather(turn("on", True, 0.02), turn("off", False, 0.01))

    assert seen == {"on": True, "off": False}


from infrastructure.chat.tools.retrieval_tools import ToolRegistry


class _StubLiteratureClient:
    pass


def _literature_registry() -> ToolRegistry:
    return ToolRegistry(
        hierarchical_search=None,
        summary_search=None,
        page_read_model=None,
        literature_client=_StubLiteratureClient(),
        literature_only=True,
    )


def test_plot_literature_is_hidden_when_stats_is_off():
    # Not merely refused on execution: the model must never see a tool it may
    # not call, or every turn pays for the description in tokens.
    names = {d.name for d in _literature_registry().definitions}
    assert "search_literature" in names
    assert "plot_literature" not in names


def test_plot_literature_appears_when_stats_is_on():
    token = set_stats_enabled(True)
    try:
        names = {d.name for d in _literature_registry().definitions}
        assert "plot_literature" in names
    finally:
        reset_stats_enabled(token)


def test_the_corpus_registry_is_unchanged_by_the_stats_flag():
    # Deep Research must be byte-identical with Stats off, and with it on: no
    # corpus tool is stats-gated, so the flag must not touch that surface at all.
    registry = ToolRegistry(
        hierarchical_search=object(),
        summary_search=object(),
        page_read_model=object(),
    )
    off = {d.name for d in registry.definitions}
    token = set_stats_enabled(True)
    try:
        on = {d.name for d in registry.definitions}
    finally:
        reset_stats_enabled(token)
    assert off == on
