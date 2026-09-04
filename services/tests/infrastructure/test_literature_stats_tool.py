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
    record_searched_query,
    reset_panel_budget,
    reset_searched_queries,
    restore_panel_budget,
    restore_searched_queries,
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
        self.cited_queries: list[str] = []

    async def year_counts(
        self, query: str, *, since: int = 1990, per_year: bool = True,
    ) -> YearCounts:
        self.queries.append(query)
        return YearCounts(
            query=query,
            # Above every _MIN_RECORDS floor: the fixtures used to hold five
            # papers, which the thin-set guard now refuses on sight.
            total=42,
            counts={2019: 20, 2020: 22},
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

    async def top_cited(self, query: str, *, limit: int = 40) -> list[LiteratureHit]:
        self.cited_queries.append(query)
        return [
            LiteratureHit(
                external_id="1", source="MED", title="A paper",
                year=2019, cited_by_count=7, pub_types=("research-article",),
            ),
        ]

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
    assert (2020.0, 22.0) in block.chart.series[0].points
    # The summary the model reads describes the shape, never the whole series:
    # it is what survives into history, inside answer_synthesis's 500 chars.
    assert "42" in summary
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
    # Distinct subjects each time: the same panel over the same subjects is
    # refused by the duplicate guard before the budget is ever consulted.
    args = {"panel": "timeline", "facets": [{"name": "a", "query": "x"}]}

    for i in range(MAX_PANELS_PER_TURN):
        _r, _s, events = await tool.execute(
            {"panel": "timeline", "facets": [{"name": "a", "query": f"q{i}"}]},
            uuid4(),
            None,
        )
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

    async def year_counts(
        self, query: str, *, since: int = 1990, per_year: bool = True,
    ) -> YearCounts:
        return YearCounts(query=query, total=999_999, counts={}, records=[], exhaustive=False)


class _MultiTypeClient:
    """One facet whose records span every pub-type bucket."""

    async def year_counts(
        self, query: str, *, since: int = 1990, per_year: bool = True,
    ) -> YearCounts:
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
        # Padded past the evidence_mix floor with plain articles: the panel is
        # about proportions, and four papers has none worth drawing.
        records += [
            LiteratureHit(
                external_id=f"pad{i}", source="MED", title="Padding",
                year=2020, cited_by_count=1, pub_types=("research-article",),
            )
            for i in range(20)
        ]
        return YearCounts(
            query=query,
            total=len(records),
            counts={2020: 22, 2018: 1, 2021: 1},
            records=records,
            exhaustive=True,
        )

    async def top_cited(self, query: str, *, limit: int = 40) -> list[LiteratureHit]:
        counts = await self.year_counts(query)
        return sorted(counts.records, key=lambda r: -r.cited_by_count)[:limit]


class _MixedExhaustivenessClient:
    """One facet's query matches few enough records to be exhaustive; the other doesn't."""

    async def year_counts(
        self, query: str, *, since: int = 1990, per_year: bool = True,
    ) -> YearCounts:
        if query == "exhaustive":
            return YearCounts(
                query=query,
                total=30,
                counts={2020: 30},
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

    async def year_counts(
        self, query: str, *, since: int = 1990, per_year: bool = True,
    ) -> YearCounts:
        raise self._exc

    async def top_cited(self, query: str, *, limit: int = 40) -> list[LiteratureHit]:
        raise self._exc


class _BucketCountingClient:
    """Over the exhaustive limit, so evidence_mix must count buckets server-side."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def year_counts(
        self, query: str, *, since: int = 1990, per_year: bool = True,
    ) -> YearCounts:
        self.queries.append(query)
        lowered = query.lower()
        if 'pub_type:"review"' in lowered:
            counts = {2020: 40, 2021: 60}
        elif "src:ppr" in lowered:
            counts = {2021: 15}
        elif "not pub_type" in lowered:
            counts = {2020: 300, 2021: 500}
        else:  # the bare facet, counted only for its total
            counts = {}
        return YearCounts(
            query=query,
            total=sum(counts.values()) or 915,
            counts=counts,
            records=[],
            exhaustive=False,
        )


async def test_evidence_mix_above_the_exhaustive_limit_counts_buckets_server_side():
    # The panel used to require every facet exhaustive, which meant it drew only
    # for topics too narrow for anyone to ask whether they were primary work.
    # It was attempted three times in the live pass and drew zero times.
    client = _BucketCountingClient()
    tool = PlotLiteratureTool(client)
    _r, _s, events = await tool.execute(
        {"panel": "evidence_mix", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert len(events) == 1
    chart = events[0].block.chart
    assert {s.name for s in chart.series} == {"Review", "Preprint", "Research article"}
    review = next(s for s in chart.series if s.name == "Review")
    assert (2021.0, 60.0) in review.points
    # One sweep per bucket over the merged facets, not one per facet.
    assert sum('and pub_type:"review"' in q.lower() for q in client.queries) == 1


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


async def test_a_mixed_regime_evidence_mix_counts_rather_than_using_partial_records():
    # One facet's records are in hand and the other's are not. Bucketing the
    # records it has would draw a mix of one facet and call it both.
    client = _BucketCountingClient()
    tool = PlotLiteratureTool(client)
    _r, _s, events = await tool.execute(
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
    assert len(events) == 1
    # Both facets are merged into each bucket sweep, so neither is dropped.
    review = next(q for q in client.queries if 'and pub_type:"review"' in q.lower())
    assert "exhaustive" in review
    assert "too many" in review


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

    async def year_counts(
        self, query: str, *, since: int = 1990, per_year: bool = True,
    ) -> YearCounts:
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

    async def year_counts(
        self, query: str, *, since: int = 1990, per_year: bool = True,
    ) -> YearCounts:
        return YearCounts(
            query=query,
            total=15158,
            counts={2020: 500, 2021: 700},
            records=[],
            exhaustive=False,
        )


class _SharedRecordClient:
    """Two facets whose queries both match the same paper."""

    async def year_counts(
        self, query: str, *, since: int = 1990, per_year: bool = True,
    ) -> YearCounts:
        return YearCounts(
            query=query,
            total=30,
            counts={2020: 30},
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


async def test_a_year_filtered_facet_is_refused_before_any_request():
    client = _StubClient()
    tool = PlotLiteratureTool(client)
    _r, summary, events = await tool.execute(
        {
            "panel": "timeline",
            "facets": [{"name": "a", "query": 'x AND PUB_YEAR:[2020 TO 2024]'}],
        },
        uuid4(),
        None,
    )
    assert events == []
    assert client.queries == []
    assert "PUB_YEAR" in summary


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


# ── The guards added after the 2026-09-04 live pass ──


class _ThinClient:
    """A real but tiny match: three papers, one per year."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def year_counts(
        self, query: str, *, since: int = 1990, per_year: bool = True,
    ) -> YearCounts:
        self.queries.append(query)
        records = [
            LiteratureHit(external_id=str(i), source="MED", title="A paper", year=2018 + i)
            for i in range(3)
        ]
        return YearCounts(
            query=query,
            total=3,
            counts={2018: 1, 2019: 1, 2020: 1},
            records=records,
            exhaustive=True,
        )

    async def search_or_raise(self, query: str, *, limit: int = 25) -> list[LiteratureHit]:
        return []


async def test_a_timeline_over_three_papers_is_refused_rather_than_drawn_flat():
    # Measured twice in the live pass: three bars of height one with a 0-to-1
    # y-axis, which invites a trend to be read out of the paper list.
    tool = PlotLiteratureTool(_ThinClient())
    _r, summary, events = await tool.execute(
        {"panel": "timeline", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert events == []
    assert "3 papers" in summary
    assert "15" in summary


async def test_a_thin_stance_panel_is_refused_before_the_classifier_is_called():
    # The floor sits before the dispatch, not after it: by the time _stance has
    # built a spec it has already refetched core records and spent an LLM call
    # on the user's own key.
    calls: list[str] = []

    class _CountingLLM:
        async def complete(self, prompt: str, **kwargs) -> str:
            calls.append(prompt)
            return '{"verdicts": []}'

    tool = PlotLiteratureTool(_ThinClient(), stance_llm=_CountingLLM())
    _r, _s, events = await tool.execute(
        {"panel": "stance", "claim": "a claim", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert events == []
    assert calls == []


async def test_a_facet_built_from_a_retrieved_title_is_refused_before_any_request():
    # The measured failure: the searches ran a subject query, the facets came
    # back as the titles of the papers those searches returned, and the chart
    # counted a population the answer had never read.
    token = reset_searched_queries()
    try:
        record_searched_query('TITLE_ABS:"MmpL3" AND TITLE_ABS:"proton motive force"')
        client = _StubClient()
        tool = PlotLiteratureTool(client)
        _r, summary, events = await tool.execute(
            {
                "panel": "timeline",
                "facets": [{"name": "a", "query": 'TITLE_ABS:"Direct Inhibition of MmpL3"'}],
            },
            uuid4(),
            None,
        )
        assert events == []
        assert client.queries == []
        assert "Direct Inhibition of MmpL3" in summary
    finally:
        restore_searched_queries(token)


async def test_a_facet_reusing_a_searched_subject_is_allowed():
    token = reset_searched_queries()
    try:
        record_searched_query('TITLE_ABS:"MmpL3" AND PUB_YEAR:[2010 TO 2026]')
        tool = PlotLiteratureTool(_StubClient())
        _r, _s, events = await tool.execute(
            {"panel": "timeline", "facets": [{"name": "a", "query": 'TITLE_ABS:"MmpL3"'}]},
            uuid4(),
            None,
        )
        assert len(events) == 1
    finally:
        restore_searched_queries(token)


async def test_a_date_windowed_facet_is_refused_whichever_field_it_uses():
    # The rule is "no date filter", not "no PUB_YEAR": a FIRST_PDATE window
    # truncates the series exactly the same way.
    client = _StubClient()
    tool = PlotLiteratureTool(client)
    _r, summary, events = await tool.execute(
        {
            "panel": "timeline",
            "facets": [{"name": "a", "query": "x AND FIRST_PDATE:[2015-01-01 TO 2026-12-31]"}],
        },
        uuid4(),
        None,
    )
    assert events == []
    assert client.queries == []
    assert "date" in summary.lower()


async def test_the_same_panel_over_the_same_subjects_is_not_redrawn():
    # The turn's grounding retry reruns retrieval from scratch and replots the
    # first pass's chart, usually with a facet dropped, spending the second
    # budget slot on a strictly worse copy.
    tool = PlotLiteratureTool(_StubClient())
    _r, _s, first = await tool.execute(
        {
            "panel": "timeline",
            "facets": [{"name": "a", "query": "x"}, {"name": "b", "query": "y"}],
        },
        uuid4(),
        None,
    )
    assert len(first) == 1
    _r, summary, second = await tool.execute(
        {"panel": "timeline", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    assert second == []
    assert "already drawn" in summary.lower()


async def test_two_facets_sharing_a_name_are_refused_rather_than_silently_merged():
    client = _StubClient()
    tool = PlotLiteratureTool(client)
    _r, summary, events = await tool.execute(
        {
            "panel": "timeline",
            "facets": [{"name": "Papers", "query": "x"}, {"name": "Papers", "query": "y"}],
        },
        uuid4(),
        None,
    )
    assert events == []
    assert client.queries == []
    assert "name" in summary.lower()


class _GappyClient:
    """A field that stopped publishing for a decade and started again."""

    async def year_counts(
        self, query: str, *, since: int = 1990, per_year: bool = True,
    ) -> YearCounts:
        return YearCounts(
            query=query,
            total=40,
            counts={2000: 20, 2010: 20},
            records=[],
            exhaustive=False,
        )


async def test_years_with_no_papers_are_drawn_as_zero_not_closed_up():
    # year_counts returns only years that have papers and the bar chart's axis
    # is categorical, so a decade of silence rendered as two adjacent bars —
    # a dormant field drawn as continuous activity.
    tool = PlotLiteratureTool(_GappyClient())
    _r, _s, events = await tool.execute(
        {"panel": "timeline", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    points = events[0].block.chart.series[0].points
    assert len(points) == 11
    assert (2005.0, 0.0) in points


async def test_landmarks_names_the_papers_it_plots():
    # The panel exists to surface canonical papers, and without a label per
    # point the tooltip reads "Citations : 1490" over an anonymous dot.
    tool = PlotLiteratureTool(_StubClient())
    _r, _s, events = await tool.execute(
        {"panel": "landmarks", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    series = events[0].block.chart.series[0]
    assert series.labels == ["A paper"]
    assert len(series.labels) == len(series.points)


async def test_the_footnote_names_the_population_the_counts_describe():
    # The answer above is written from the abstracts that fit the context
    # budget; these counts are the whole match. Nothing else reconciles them.
    tool = PlotLiteratureTool(_StubClient())
    _r, _s, events = await tool.execute(
        {"panel": "timeline", "facets": [{"name": "a", "query": "x"}]},
        uuid4(),
        None,
    )
    footnote = events[0].block.chart.footnote
    assert "42" in footnote
    assert "not only the papers cited above" in footnote
