"""A chart block is an ordinary content block, and must stay one.

The point of these tests is that nothing bespoke was added: the same DTO the
table and molecule blocks travel in carries a chart, so streaming, persistence
and conversation reopen all keep working without new code.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from application.dtos.chat_dtos import AgentEvent, ChartSeriesDTO, ChartSpecDTO, ContentBlockDTO


def _spec() -> ChartSpecDTO:
    return ChartSpecDTO(
        panel="timeline",
        title="Papers per year",
        x_label="Year",
        y_label="Papers",
        series=[
            ChartSeriesDTO(name="Proton motive force", points=[(2024.0, 1.0), (2025.0, 4.0)]),
        ],
        partial_x=2026.0,
        source_query='TITLE_ABS:"MmpL3"',
    )


def test_a_chart_travels_in_the_ordinary_content_block():
    block = ContentBlockDTO(type="chart", chart=_spec())
    assert block.type == "chart"
    assert block.chart is not None
    assert block.chart.series[0].points[1] == (2025.0, 4.0)


def test_a_chart_block_round_trips_through_json():
    # mongo_chat_repository persists blocks with model_dump(mode="json") and
    # rebuilds them with ContentBlockDTO(**b). A chart must survive that.
    original = ContentBlockDTO(type="chart", chart=_spec())
    rebuilt = ContentBlockDTO(**original.model_dump(mode="json"))
    assert rebuilt.chart == original.chart


def test_a_chart_rides_the_existing_structured_block_event():
    event = AgentEvent(type="structured_block", block=ContentBlockDTO(type="chart", chart=_spec()))
    assert event.block is not None
    assert event.block.chart is not None


def test_an_unknown_panel_is_refused():
    # The renderer switches on panel; an unknown value would render nothing at
    # all, silently. Fail at the boundary instead.
    with pytest.raises(ValidationError):
        ChartSpecDTO(
            panel="sunburst",
            title="x",
            x_label="x",
            y_label="y",
            series=[],
        )
