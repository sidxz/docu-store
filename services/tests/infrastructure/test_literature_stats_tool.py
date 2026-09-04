"""Charting a result set as a tool.

The two things worth pinning are that the tool computes every number itself,
and that the two-panel maximum is a counter rather than a request in a prompt.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from infrastructure.chat.tools.literature_stats_tools import (
    PlotLiteratureTool,
    bucket_pub_type,
)
from infrastructure.literature.europe_pmc import (
    LiteratureHit,
    LiteratureQueryError,
    LiteratureSourceUnavailableError,
    YearCounts,
)
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
        self.core_queries: list[str] = []

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

    async def search_or_raise(self, query: str, *, limit: int = 25) -> list[LiteratureHit]:
        # The counting path is resultType=lite and carries no abstract; stance
        # re-fetches core records through here to get one.
        self.core_queries.append(query)
        return [
            LiteratureHit(
                external_id="1",
                source="MED",
                title="A paper",
                abstract="MmpL3 inhibitors act directly on the transporter.",
                year=2019,
            ),
        ]


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


class _NonExhaustiveClient:
    """Above the exhaustive limit: counts only, no individual records."""

    async def year_counts(self, query: str, *, since: int = 1990) -> YearCounts:
        return YearCounts(query=query, total=999_999, counts={}, records=[], exhaustive=False)


class _MultiTypeClient:
    """One facet whose records span every pub-type bucket."""

    async def year_counts(self, query: str, *, since: int = 1990) -> YearCounts:
        records = [
            LiteratureHit(
                external_id="1", source="MED", title="Article",
                year=2020, cited_by_count=3, pub_types=("research-article",),
            ),
            LiteratureHit(
                external_id="2", source="MED", title="Review",
                year=2020, cited_by_count=50, pub_types=("review",),
            ),
            LiteratureHit(
                external_id="3", source="PAT", title="Patent",
                year=2018, cited_by_count=0, pub_types=("patent",),
            ),
            LiteratureHit(
                external_id="4", source="PPR", title="Preprint",
                year=2021, cited_by_count=1, pub_types=("preprint",),
            ),
        ]
        return YearCounts(
            query=query,
            total=len(records),
            counts={2020: 2, 2018: 1, 2021: 1},
            records=records,
            exhaustive=True,
        )


class _MixedExhaustivenessClient:
    """One facet's query matches few enough records to be exhaustive; the other doesn't."""

    async def year_counts(self, query: str, *, since: int = 1990) -> YearCounts:
        if query == "exhaustive":
            return YearCounts(
                query=query,
                total=1,
                counts={2020: 1},
                records=[
                    LiteratureHit(
                        external_id="1", source="MED", title="A",
                        year=2020, cited_by_count=1, pub_types=("research-article",),
                    ),
                ],
                exhaustive=True,
            )
        return YearCounts(query=query, total=999_999, counts={}, records=[], exhaustive=False)


class _RaisingClient:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def year_counts(self, query: str, *, since: int = 1990) -> YearCounts:
        raise self._exc


async def test_a_non_exhaustive_evidence_mix_is_refused_with_no_event():
    tool = PlotLiteratureTool(_NonExhaustiveClient())
    _r, summary, events = await tool.execute(
        {"panel": "evidence_mix", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert events == []
    assert "narrow" in summary.lower()


async def test_a_refused_evidence_mix_does_not_burn_a_panel_slot():
    tool = PlotLiteratureTool(_NonExhaustiveClient())
    for _ in range(MAX_PANELS_PER_TURN + 1):
        _r, _s, events = await tool.execute(
            {"panel": "evidence_mix", "facets": [{"name": "a", "query": "x"}]},
            uuid4(),
            None,
        )
        assert events == []

    # The budget was never touched by the refusals above, so a timeline still draws.
    tool2 = PlotLiteratureTool(_StubClient())
    _r, _s, events = await tool2.execute(
        {"panel": "timeline", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert len(events) == 1


async def test_evidence_mix_refuses_when_only_some_facets_are_exhaustive():
    tool = PlotLiteratureTool(_MixedExhaustivenessClient())
    _r, summary, events = await tool.execute(
        {
            "panel": "evidence_mix",
            "facets": [
                {"name": "Exhaustive", "query": "exhaustive"},
                {"name": "TooMany", "query": "too many"},
            ],
        },
        uuid4(),
        None,
    )
    assert events == []
    assert "narrow" in summary.lower()


async def test_evidence_mix_buckets_records_by_pub_type():
    tool = PlotLiteratureTool(_MultiTypeClient())
    _r, _s, events = await tool.execute(
        {"panel": "evidence_mix", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert len(events) == 1
    chart = events[0].block.chart
    assert chart.panel == "evidence_mix"
    names = {s.name for s in chart.series}
    assert names == {"Research article", "Review", "Patent", "Preprint"}
    patent_series = next(s for s in chart.series if s.name == "Patent")
    assert (2018.0, 1.0) in patent_series.points


async def test_landmarks_plots_citations_against_year():
    tool = PlotLiteratureTool(_MultiTypeClient())
    _r, _s, events = await tool.execute(
        {"panel": "landmarks", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert len(events) == 1
    chart = events[0].block.chart
    assert chart.panel == "landmarks"
    assert (2020.0, 50.0) in chart.series[0].points


def test_bucket_pub_type_prefers_review_over_journal_article():
    assert bucket_pub_type("research support, non-u.s. gov't; review; journal article") == "Review"


def test_bucket_pub_type_recognises_a_patent():
    assert bucket_pub_type("patent") == "Patent"


async def test_a_rejected_query_reaches_the_model_as_readable_guidance():
    tool = PlotLiteratureTool(_RaisingClient(LiteratureQueryError("bad syntax")))
    _r, summary, events = await tool.execute(
        {"panel": "timeline", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert events == []
    assert "rejected" in summary.lower()


async def test_a_source_outage_reaches_the_model_as_readable_guidance():
    tool = PlotLiteratureTool(_RaisingClient(LiteratureSourceUnavailableError("503")))
    _r, summary, events = await tool.execute(
        {"panel": "timeline", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert events == []
    assert "unreachable" in summary.lower()


async def test_a_stance_panel_stacks_labels_by_year():
    from infrastructure.chat.tools.literature_stats_tools import PlotLiteratureTool

    class _StanceLLM:
        async def complete(self, prompt: str, **kwargs) -> str:
            return '{"verdicts": [{"id": "1", "label": "refutes", "evidence": "directly"}]}'

    tool = PlotLiteratureTool(_StubClient(), stance_llm=_StanceLLM())
    _r, summary, events = await tool.execute(
        {
            "panel": "stance",
            "claim": "MmpL3 inhibitors act by disrupting the proton motive force",
            "facets": [{"name": "MmpL3", "query": 'TITLE_ABS:"MmpL3"'}],
        },
        uuid4(),
        None,
    )
    spec = events[0].block.chart
    assert spec.panel == "stance"
    assert {s.name for s in spec.series} <= {"supports", "refutes", "mixed", "none"}
    assert (2019.0, 1.0) in [p for s in spec.series if s.name == "refutes" for p in s.points]


async def test_a_stance_panel_without_a_claim_is_refused():
    tool = PlotLiteratureTool(_StubClient())
    _r, summary, events = await tool.execute(
        {"panel": "stance", "facets": [{"name": "a", "query": "x"}]}, uuid4(), None,
    )
    assert events == []
    assert "claim" in summary.lower()


class _ManyHitsClient:
    """One facet, exhaustively fetched, matching more than the stance reading cap."""

    def __init__(self, count: int) -> None:
        self._count = count

    async def year_counts(self, query: str, *, since: int = 1990) -> YearCounts:
        records = [
            LiteratureHit(external_id=str(i), source="MED", title="A paper", year=2020)
            for i in range(self._count)
        ]
        return YearCounts(
            query=query,
            total=self._count,
            counts={2020: self._count},
            records=records,
            exhaustive=True,
        )


async def test_a_stance_panel_over_the_reading_cap_is_refused_without_calling_the_classifier():
    calls: list[str] = []

    class _CountingLLM:
        async def complete(self, prompt: str, **kwargs) -> str:
            calls.append(prompt)
            return '{"verdicts": []}'

    tool = PlotLiteratureTool(_ManyHitsClient(61), stance_llm=_CountingLLM())
    _r, summary, events = await tool.execute(
        {"panel": "stance", "claim": "a claim", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert events == []
    assert calls == []
    assert "narrow" in summary.lower()
    assert "61" in summary


async def test_a_stance_panel_whose_classifier_raises_is_refused_readably():
    class _RaisingLLM:
        async def complete(self, prompt: str, **kwargs) -> str:
            raise RuntimeError("provider timed out")

    tool = PlotLiteratureTool(_StubClient(), stance_llm=_RaisingLLM())
    _r, summary, events = await tool.execute(
        {"panel": "stance", "claim": "a claim", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert events == []
    assert "failed" in summary.lower()


async def test_an_unparseable_stance_response_does_not_say_too_many_and_names_the_classifier():
    class _GibberishLLM:
        async def complete(self, prompt: str, **kwargs) -> str:
            return "not json"

    tool = PlotLiteratureTool(_StubClient(), stance_llm=_GibberishLLM())
    _r, summary, events = await tool.execute(
        {"panel": "stance", "claim": "a claim", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert events == []
    assert "too many" not in summary.lower()
    assert "classifier" in summary.lower()


# ── The lite/core split, the fan-out ceiling, and the honest footnote ──


class _NonExhaustiveWithCountsClient:
    """Over the exhaustive limit: real per-year counts, but only from `since`."""

    async def year_counts(self, query: str, *, since: int = 1990) -> YearCounts:
        return YearCounts(
            query=query,
            total=15158,
            counts={2020: 500, 2021: 700},
            records=[],
            exhaustive=False,
        )


class _SharedRecordClient:
    """Two facets whose queries both match the same paper."""

    async def year_counts(self, query: str, *, since: int = 1990) -> YearCounts:
        return YearCounts(
            query=query,
            total=1,
            counts={2020: 1},
            records=[
                LiteratureHit(
                    external_id="shared", source="MED", title="Both facets match this",
                    year=2020, cited_by_count=9, pub_types=("research-article",),
                ),
            ],
            exhaustive=True,
        )

    async def search_or_raise(self, query: str, *, limit: int = 25) -> list[LiteratureHit]:
        return [
            LiteratureHit(
                external_id="shared", source="MED", title="Both facets match this",
                abstract="An abstract.", year=2020,
            ),
        ]


async def test_a_record_matched_by_two_facets_is_counted_once():
    # Facets overlap constantly -- two sides of one question share papers. Left
    # undeduped, the shared paper is drawn twice and every total is inflated.
    tool = PlotLiteratureTool(_SharedRecordClient())
    _r, _s, events = await tool.execute(
        {
            "panel": "evidence_mix",
            "facets": [{"name": "a", "query": "x"}, {"name": "b", "query": "y"}],
        },
        uuid4(),
        None,
    )
    series = events[0].block.chart.series
    assert [p for s in series for p in s.points] == [(2020.0, 1.0)]


async def test_a_non_exhaustive_timeline_says_where_its_counts_start():
    # The per-year path counts from 1990 only, so "the whole Europe PMC match"
    # would be a lie by a few thousand papers.
    tool = PlotLiteratureTool(_NonExhaustiveWithCountsClient())
    _r, _s, events = await tool.execute(
        {"panel": "timeline", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    footnote = events[0].block.chart.footnote
    assert "1990" in footnote
    assert "15,158" in footnote


async def test_more_than_three_facets_is_refused_before_any_request():
    client = _StubClient()
    tool = PlotLiteratureTool(client)
    _r, summary, events = await tool.execute(
        {
            "panel": "timeline",
            "facets": [{"name": str(i), "query": f"q{i}"} for i in range(4)],
        },
        uuid4(),
        None,
    )
    assert events == []
    assert client.queries == []
    assert "facet" in summary.lower()


async def test_a_chart_with_no_points_at_all_is_refused_rather_than_drawn_empty():
    tool = PlotLiteratureTool(_NonExhaustiveClient())
    _r, summary, events = await tool.execute(
        {"panel": "timeline", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert events == []
    assert "no papers" in summary.lower()


# ── Stance: abstracts, evidence, and the shape the model is told ──


class _RecordingStanceLLM:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    async def complete(self, prompt: str, **kwargs) -> str:
        self.prompts.append(prompt)
        return self.payload


async def test_stance_classifies_abstracts_refetched_as_core_not_lite_titles():
    # year_counts uses resultType=lite, whose records have no abstractText at
    # all, while the classifier prompt demands a verbatim abstract quote.
    client = _StubClient()
    llm = _RecordingStanceLLM('{"verdicts": [{"id": "1", "label": "refutes", "evidence": "act directly"}]}')
    tool = PlotLiteratureTool(client, stance_llm=llm)
    _r, _s, events = await tool.execute(
        {"panel": "stance", "claim": "a claim", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert client.core_queries == ["x"]
    assert "act directly on the transporter" in llm.prompts[0]
    assert len(events) == 1


async def test_stance_ships_the_fragment_that_decided_each_verdict():
    llm = _RecordingStanceLLM('{"verdicts": [{"id": "1", "label": "refutes", "evidence": "act directly"}]}')
    tool = PlotLiteratureTool(_StubClient(), stance_llm=llm)
    _r, _s, events = await tool.execute(
        {"panel": "stance", "claim": "a claim", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    notes = events[0].block.chart.notes
    assert notes and "act directly" in notes[0]
    assert "refutes" in notes[0]


async def test_the_model_is_told_the_stance_split_and_when_it_turned():
    llm = _RecordingStanceLLM('{"verdicts": [{"id": "1", "label": "refutes", "evidence": "act directly"}]}')
    tool = PlotLiteratureTool(_StubClient(), stance_llm=llm)
    _r, summary, _e = await tool.execute(
        {"panel": "stance", "claim": "a claim", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert "refutes" in summary
    assert "2019" in summary


async def test_a_long_claim_does_not_become_a_paragraph_of_chart_title():
    llm = _RecordingStanceLLM('{"verdicts": [{"id": "1", "label": "none", "evidence": ""}]}')
    tool = PlotLiteratureTool(_StubClient(), stance_llm=llm)
    claim = "x" * 400
    _r, _s, events = await tool.execute(
        {"panel": "stance", "claim": claim, "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert len(events[0].block.chart.title) < 160


async def test_a_long_claim_is_truncated_at_a_word_boundary_not_mid_word():
    llm = _RecordingStanceLLM('{"verdicts": [{"id": "1", "label": "none", "evidence": ""}]}')
    tool = PlotLiteratureTool(_StubClient(), stance_llm=llm)
    claim = " ".join(["word"] * 40)  # 199 chars, well over the 120 cap
    _r, _s, events = await tool.execute(
        {"panel": "stance", "claim": claim, "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    title = events[0].block.chart.title
    assert title.endswith("…")
    assert title == "Papers on: " + " ".join(["word"] * 24) + "…"


async def test_a_stance_facet_whose_refetch_fails_is_refused_readably():
    class _RefetchFails(_StubClient):
        async def search_or_raise(self, query: str, *, limit: int = 25):
            raise LiteratureSourceUnavailableError("503")

    llm = _RecordingStanceLLM('{"verdicts": []}')
    tool = PlotLiteratureTool(_RefetchFails(), stance_llm=llm)
    _r, summary, events = await tool.execute(
        {"panel": "stance", "claim": "a claim", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert events == []
    assert llm.prompts == []
    assert "unreachable" in summary.lower()
