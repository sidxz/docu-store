"""Charting a result set as a tool.

The two things worth pinning are that the tool computes every number itself,
and that the two-panel maximum is a counter rather than a request in a prompt.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from infrastructure.chat.tools.literature_stats_tools import PlotLiteratureTool
from infrastructure.literature.europe_pmc import LiteratureHit, YearCounts
from infrastructure.llm.stats_context import (
    MAX_PANELS_PER_TURN,
    reset_panel_budget,
    restore_panel_budget,
)


@pytest.fixture(autouse=True)
def fresh_panel_budget():
    """Every test is its own turn, so every test starts with a full budget."""
    token = reset_panel_budget()
    yield
    restore_panel_budget(token)


class _StubClient:
    """Returns canned counts and records what it was asked."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def year_counts(self, query: str, *, since: int = 1990) -> YearCounts:
        self.queries.append(query)
        return YearCounts(
            query=query,
            total=5,
            counts={2019: 2, 2020: 3},
            records=[
                LiteratureHit(
                    external_id="1",
                    source="MED",
                    title="A paper",
                    year=2019,
                    cited_by_count=7,
                    pub_types=("research-article",),
                ),
            ],
            exhaustive=True,
        )


async def test_a_timeline_emits_one_chart_block_per_facet_as_a_series():
    tool = PlotLiteratureTool(_StubClient())
    _results, summary, events = await tool.execute(
        {
            "panel": "timeline",
            "facets": [
                {"name": "PMF", "query": 'TITLE_ABS:"MmpL3" AND TITLE_ABS:"PMF"'},
                {"name": "Structure", "query": 'TITLE_ABS:"MmpL3" AND TITLE_ABS:"structure"'},
            ],
        },
        uuid4(),
        None,
    )

    assert len(events) == 1
    block = events[0].block
    assert block is not None
    assert block.type == "chart"
    assert block.chart.panel == "timeline"
    assert [s.name for s in block.chart.series] == ["PMF", "Structure"]
    assert (2020.0, 3.0) in block.chart.series[0].points
    # The summary the model reads describes the shape, never the whole series:
    # it is what survives into history, inside answer_synthesis's 500 chars.
    assert "5" in summary
    assert len(summary) < 600


async def test_the_query_reaching_europe_pmc_is_the_one_the_model_supplied():
    client = _StubClient()
    tool = PlotLiteratureTool(client)
    query = 'TITLE_ABS:"Pks13" AND TITLE_ABS:"inhibitor"'
    await tool.execute(
        {"panel": "timeline", "facets": [{"name": "Pks13", "query": query}]},
        uuid4(),
        None,
    )
    assert client.queries == [query]


async def test_the_third_panel_in_one_turn_is_refused():
    tool = PlotLiteratureTool(_StubClient())
    args = {"panel": "timeline", "facets": [{"name": "a", "query": "x"}]}

    for _ in range(MAX_PANELS_PER_TURN):
        _r, _s, events = await tool.execute(args, uuid4(), None)
        assert len(events) == 1

    _r, summary, events = await tool.execute(args, uuid4(), None)
    assert events == []
    assert "maximum" in summary.lower()


async def test_a_fresh_turn_gets_a_fresh_budget():
    # The singleton trap: a counter on the tool would exhaust once and refuse
    # for the life of the process.
    tool = PlotLiteratureTool(_StubClient())
    args = {"panel": "timeline", "facets": [{"name": "a", "query": "x"}]}
    for _ in range(MAX_PANELS_PER_TURN):
        await tool.execute(args, uuid4(), None)

    token = reset_panel_budget()
    try:
        _r, _s, events = await tool.execute(args, uuid4(), None)
        assert len(events) == 1
    finally:
        restore_panel_budget(token)


async def test_the_current_year_is_marked_partial():
    from datetime import UTC, datetime

    tool = PlotLiteratureTool(_StubClient())
    _r, _s, events = await tool.execute(
        {"panel": "timeline", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert events[0].block.chart.partial_x == float(datetime.now(UTC).year)


async def test_a_panel_with_no_facets_is_refused_without_calling_europe_pmc():
    client = _StubClient()
    tool = PlotLiteratureTool(client)
    _r, summary, events = await tool.execute({"panel": "timeline", "facets": []}, uuid4(), None)
    assert events == []
    assert client.queries == []
    assert "facet" in summary.lower()
