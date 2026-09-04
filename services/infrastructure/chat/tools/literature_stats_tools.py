"""Charting a Europe PMC result set, as a tool.

The division of labour is the whole design. The model chooses the panel and
writes the queries -- it is good at that, and the evaluation shows fielded query
construction is this surface's strongest behaviour. The tool runs them and
computes every number. No datum on a chart originates in model output, which is
the same split that keeps molecule blocks honest.

The counts describe the whole match rather than the papers retrieval fetched.
Histogramming the fetched page describes the reranker: a query matching 15,158
records returns a first page that is almost entirely the current year.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from application.dtos.chat_dtos import (
    AgentEvent,
    ChartSeriesDTO,
    ChartSpecDTO,
    ContentBlockDTO,
)
from application.ports.tool_calling_llm import ToolDefinition
from infrastructure.chat.tools.literature_tools import _outage_summary, _rejected_summary
from infrastructure.literature.europe_pmc import (
    LiteratureQueryError,
    LiteratureSourceUnavailableError,
)
from infrastructure.llm.stats_context import (
    MAX_PANELS_PER_TURN,
    claim_panel_slot,
    panel_already_drawn,
    panel_budget_spent,
    searched_queries,
)

if TYPE_CHECKING:
    from infrastructure.chat.models import RetrievalResult

log = structlog.get_logger()

# The budget itself lives in stats_context, because it must reset every turn and
# this tool is a DI singleton. Enforced as a counter rather than asked for in the
# description -- a prompt does not hold across a five-iteration agent loop.

PLOT_LITERATURE_DEF = ToolDefinition(
    name="plot_literature",
    description=(
        "Chart the papers a query matches, when the question's shape calls for a "
        "picture rather than a list. You choose the panel and write the queries; "
        "the counts are computed from Europe PMC, not by you.\n\n"
        "Call this AFTER searching and BEFORE finish_retrieval, at most twice in a "
        "turn — one panel is the normal answer. The reader asked for a chart: draw "
        "when the question is about a body of literature, and skip it when the "
        "question asks for a single fact about one thing — a structure, an "
        "identifier, a single value — where there is no body of literature to "
        "picture.\n\n"
        "Panels:\n"
        "  timeline    — volume over time. For 'is this growing', 'what is new', "
        "and for when the question asks how one thing gave way to another. Each "
        "facet becomes a series drawn across the whole span.\n"
        "  evidence_mix— research articles vs reviews vs preprints over time. For "
        "'is this primary work', and for seeing whether a field's recent growth is "
        "new results or people reviewing each other.\n"
        "  landmarks   — citations against year. For settled knowledge, where a "
        "timeline is noise and the reader needs the canonical papers.\n"
        "  stance      — how each paper stands on a CLAIM, over time. Only when the "
        "question contains a claim to adjudicate. Requires 'claim'.\n\n"
        'Pass facets as [{"name": "short label", "query": "a fielded Europe '
        'PMC query"}]. Use the same fielded queries you searched with, minus any '
        "year filter: the subject terms must match so the chart and the listed "
        "papers describe the same topic, but the years belong to the chart's axis. "
        "A facet is a subject, not a period. Sibling facets must differ in what "
        "they count, never in when; two facets that differ only by date share no "
        "year and compare nothing. When the question contrasts two periods, facet "
        "by whatever the question contrasts and let the whole span show the change.\n\n"
        "Examples:\n"
        '  do MmpL3 inhibitors disrupt PMF or bind directly  ->  timeline, facets '
        '[{"name":"PMF","query":"TITLE_ABS:\\"MmpL3\\" AND TITLE_ABS:\\"proton '
        'motive force\\""}, {"name":"Structure","query":"TITLE_ABS:\\"MmpL3\\" AND '
        'TITLE_ABS:\\"structure\\""}]\n'
        "  what is isoniazid's mechanism of action  ->  landmarks"
    ),
    parameters={
        "type": "object",
        "properties": {
            "panel": {
                "type": "string",
                "enum": ["timeline", "evidence_mix", "landmarks", "stance"],
                "description": "Which picture to draw",
            },
            "claim": {
                "type": "string",
                "description": "For panel=stance only: the claim in the user's question, as a single assertive sentence.",
            },
            "facets": {
                "type": "array",
                "description": (
                    "Which papers to count. Each facet is a subject with a short label and a "
                    "fielded query. Usually one; two when the question sets two subjects "
                    "against each other. Only the timeline panel draws one series per facet; "
                    "the others merge the facets and split the series their own way. Never one "
                    "facet per date range."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "query": {"type": "string"},
                    },
                    "required": ["name", "query"],
                },
            },
        },
        "required": ["panel", "facets"],
    },
)

_PUB_TYPE_BUCKETS = (
    ("patent", "Patent"),
    ("preprint", "Preprint"),
    ("review", "Review"),
)

# A reading budget on the user's own key: refuse rather than sample, because a
# sampled chart would claim to have scored a population it never read.
_STANCE_MAX_HITS = 60

# A fan-out ceiling, not a design limit: above the exhaustive limit each facet
# costs one request per year since 1990, so a four-facet call is ~150 requests
# to Europe PMC for one picture nobody can read anyway.
_MAX_FACETS = 3

# The year the per-year counting regime starts from, mirroring year_counts'
# ``since``. The counts cover this year onward while ``total`` counts the whole
# match, and for an old field that gap is 29% of the papers -- so nothing may
# print ``total`` and a 1990-on span in the same sentence.
_COUNT_FLOOR_YEAR = 1990

# Bucket clauses that partition a match exactly, verified against Europe PMC:
# PROTAC 734 + 274 + 2084 == 3092; ferroptosis 6182 + 1953 + 23571 == 31706.
# The labels must match ``bucket_pub_type``'s output or the same question draws
# differently-named series either side of the exhaustive limit.
#
# No patent bucket: patents carry no TITLE_ABS-indexed text (TITLE_ABS:"PROTAC"
# AND SRC:PAT is 0 against 4.2M indexed patents), so no fielded facet query the
# model is asked to write can ever surface one.
_MIX_BUCKETS = (
    ("Preprint", "AND SRC:PPR"),
    ("Review", 'AND PUB_TYPE:"review"'),
    ("Research article", 'NOT PUB_TYPE:"review" NOT SRC:PPR'),
)

# A floor, the opposite of _STANCE_MAX_HITS. Below it a panel is a picture of
# the paper list: three papers drawn as three bars of height one, with a 0-to-1
# axis that invites a trend to be read out of nothing. Landmarks is the
# exception on purpose -- its y-axis is citations, so six canonical papers at
# 400-1200 IS the answer.
_MIN_RECORDS = {"timeline": 15, "evidence_mix": 20, "stance": 10, "landmarks": 5}

# Europe PMC honours several date fields, and the rule is "no year filter", not
# "no PUB_YEAR". A facet windowed by FIRST_PDATE truncates the series exactly as
# PUB_YEAR would, and passed the original substring check untouched.
_DATE_FIELD_RE = re.compile(
    r"\b(pub_year|first_pdate|first_idate|pub_date|ppub_pdate|electronic_pdate|creation_date)\b",
    re.IGNORECASE,
)

# Quoted phrases are how a facet smuggles in a subject nobody searched for --
# the measured failure was a retrieved paper's title re-quoted as a facet query.
_PHRASE_RE = re.compile(r'"([^"]+)"')

# Only stance still needs the records themselves; the other panels now count
# server-side. Narrowing is the one recovery a model reaches for, and left
# unqualified it narrows to a single paper's title -- measured, twice.
_TOO_MANY_MSG = (
    "Stance reads the abstracts themselves, and this query matches too many to "
    "read. Narrow the SUBJECT, never the paper set: a facet naming one paper's "
    "title charts that paper alone. If the subject will not narrow without "
    "naming individual papers, use a timeline instead."
)


class _PanelRefusedError(Exception):
    """A panel could not be drawn. The message is what the model reads."""


def bucket_pub_type(raw: str | None) -> str:
    """Europe PMC's pubType is semicolon-joined free text, not an enum.

    Real values include "research support, non-u.s. gov't; research-article;
    journal article", so this matches on substrings in a deliberate order:
    a record tagged both review and journal article is a review.
    """
    lowered = (raw or "").lower()
    for needle, label in _PUB_TYPE_BUCKETS:
        if needle in lowered:
            return label
    return "Research article"


def _plural(n: int, noun: str) -> str:
    return f"{n:,} {noun}" if n == 1 else f"{n:,} {noun}s"


def _scope_footnote(counted: list[tuple[str, Any]], *, all_years: bool | None = None) -> str:
    """Whose papers these are, and over what span.

    Two things a reader cannot otherwise know. The span, because above the
    exhaustive limit the counts are per-year requests from 1990, so claiming
    "all years" would hide every paper before it -- 29% of them for
    tuberculosis. And the population, because the answer above is written from
    the handful of abstracts that fit the context budget while these counts are
    the whole Europe PMC match; a reader comparing "6 of 13" against a 3,826-bar
    chart has nothing else telling them the two describe different things.

    Mixed facets get the conservative span: one facet counted from 1990 makes
    the chart's left edge 1990, whatever its sibling reached.
    """
    # The panel knows its own span: landmarks reads the citation ranking, which
    # Europe PMC applies over the whole match, so its counts' 1990 floor says
    # nothing about what it drew.
    covers_all = (
        all(c.exhaustive for _n, c in counted) if all_years is None else all_years
    )
    span = "All years" if covers_all else f"From {_COUNT_FLOOR_YEAR} on"
    # Not a sum: facets overlap by construction, so adding them over-reports.
    totals = " · ".join(f"{n} {c.total:,}" for n, c in counted)
    return f"{span}. Every Europe PMC match ({totals}), not only the papers cited above."


def _truncate_claim(claim: str, limit: int = 120) -> str:
    """Truncate at the last space before ``limit`` chars, never mid-word."""
    if len(claim) <= limit:
        return claim
    cut = claim[:limit].rfind(" ")
    return f"{claim[: cut if cut > 0 else limit]}…"


def _densify_years(spec: ChartSpecDTO) -> None:
    """Give every year in the span a point, including the empty ones.

    ``year_counts`` returns only years that have papers, and the bar chart's
    x-axis is categorical -- it draws the values it is given, evenly spaced. A
    field with a thirty-year gap therefore renders as continuous activity:
    thiacetazone resistance spans 1963-2021 across 31 distinct years with 28
    empty ones inside it, and every one of those gaps closed up silently.

    Filled in place, over the union of the series' spans, so stacked panels
    keep a common axis. Landmarks is exempt -- it is a scatter over individual
    papers, and a year with no landmark is not a zero.
    """
    years = [int(x) for s in spec.series for x, _y in s.points]
    if not years:
        return
    span = range(min(years), max(years) + 1)
    for series in spec.series:
        have = {int(x): y for x, y in series.points}
        series.points = [(float(y), have.get(y, 0.0)) for y in span]


def _deduped_records(counted: list[tuple[str, Any]]) -> list[Any]:
    """Every record across the facets, each once.

    Facets overlap by construction -- two sides of one question share papers --
    and an undeduped concatenation draws the shared ones twice.
    """
    # Keyed by (source, id): Europe PMC ids are unique per source, not globally
    # -- a CBA record and a MED record can share a bare numeric id and name
    # different papers.
    return list({(r.source, r.external_id): r for _n, c in counted for r in c.records}.values())


class PlotLiteratureTool:
    """Computes a chart from Europe PMC counts and emits it as a content block."""

    def __init__(self, client: Any, stance_llm: Any | None = None) -> None:
        self._client = client
        self._stance_llm = stance_llm

    @property
    def definition(self) -> ToolDefinition:
        return PLOT_LITERATURE_DEF

    async def execute(
        self,
        args: dict[str, Any],
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
    ) -> tuple[list[RetrievalResult], str, list[AgentEvent]]:
        """Draw one panel. Returns no retrieval results: a chart is not evidence.

        allowed_artifact_ids is ignored, as it is for search_literature —
        published literature is not scoped to a tenant.
        """
        panel = (args.get("panel") or "").strip()
        facets = [
            f
            for f in (args.get("facets") or [])
            if isinstance(f, dict) and (f.get("query") or "").strip()
        ]
        claim = (args.get("claim") or "").strip()

        guard_error = self._validate_args(panel, facets, claim)
        if guard_error is not None:
            return [], guard_error, []

        # Peek rather than claim: the budget counts panels DRAWN, and a refusal
        # below (no data, a source error) must cost zero Europe PMC requests and
        # zero slots. The slot is claimed only once a chart is actually emitted.
        if panel_budget_spent():
            return (
                [],
                f"Panel not drawn: the maximum of {MAX_PANELS_PER_TURN} charts per "
                "answer has been reached. Answer with what you already have.",
                [],
            )
        # A turn can run retrieval twice -- the grounding retry rebuilds the
        # agent loop from scratch -- and the second pass redraws the first
        # pass's chart, usually with a facet dropped. That spent the second
        # budget slot on a strictly worse copy of the first panel.
        queries = [str(f["query"]) for f in facets]
        if panel_already_drawn(panel, queries):
            return (
                [],
                f"Panel not drawn: a {panel.replace('_', ' ')} panel over these same "
                "subjects was already drawn this turn. Draw a different panel, or "
                "answer with what you have.",
                [],
            )

        counted, error_summary = await self._count_facets(
            facets, per_year=panel == "timeline",
        )
        if error_summary is not None:
            return [], error_summary, []

        try:
            spec = await self._build_spec(panel, counted, claim)
        except _PanelRefusedError as exc:
            return [], str(exc), []

        claim_panel_slot(panel, queries)
        log.info(
            "tool.literature.plotted",
            panel=panel,
            facets=len(counted),
            total=sum(c.total for _n, c in counted),
        )
        return [], _summarise(panel, counted, spec), [
            AgentEvent(
                type="structured_block",
                block=ContentBlockDTO(type="chart", chart=spec),
            ),
        ]

    def _validate_args(  # noqa: PLR0911 -- guard clauses, one refusal each
        self, panel: str, facets: list[dict[str, Any]], claim: str,
    ) -> str | None:
        """The readable refusal for a bad call, or None when it may proceed."""
        if not facets:
            return "plot_literature needs at least one facet with a query."
        if len(facets) > _MAX_FACETS:
            return (
                f"plot_literature takes at most {_MAX_FACETS} facets; {len(facets)} "
                "were given. Pick the facets that actually contrast."
            )
        if any(_DATE_FIELD_RE.search(str(f["query"])) for f in facets):
            return (
                "Facet queries must not filter by date: the chart's x-axis is already the "
                "year, so a windowed query draws a series that stops where the filter "
                "does. Resend the same queries with the date clause removed "
                "(PUB_YEAR, FIRST_PDATE and the other date fields alike)."
            )
        if panel not in {"timeline", "evidence_mix", "landmarks", "stance"}:
            return f"Unknown panel '{panel}'. Use timeline, evidence_mix, landmarks or stance."
        names = [str(f.get("name") or "Papers") for f in facets]
        if len(set(names)) != len(names):
            return (
                "Two facets share a name, and a chart keys its series by name — they "
                "would silently merge into one. Give each facet a distinct label."
            )
        stray = self._unsearched_phrases(facets)
        if stray:
            return (
                "Facet queries must count the papers you searched. These phrases appear "
                f"in no search this turn: {', '.join(stray)}. Reuse the fielded queries "
                "you searched with, minus any date filter — do not build a facet out of "
                "the titles of the papers that came back."
            )
        if panel == "stance" and not claim:
            return "panel=stance needs a 'claim': the assertion to score papers against."
        if panel == "stance" and self._stance_llm is None:
            return "Stance classification is not configured on this deployment."
        return None

    @staticmethod
    def _unsearched_phrases(facets: list[dict[str, Any]]) -> list[str]:
        """Quoted phrases in the facets that no search this turn used.

        The rule the design calls "the counting query is the search query" no
        longer means byte equality -- a facet legitimately drops the date filter
        the search carried. What it still means is that every subject came from
        a query that actually produced cards. The measured failure was a facet
        built from a retrieved paper's own title, which passes every other
        guard and charts a population the answer never read.

        Permissive when nothing was searched: plot-before-search is a different
        defect, and refusing here would make this guard fire in every unit test
        that drives the tool directly.
        """
        searched = searched_queries()
        if not searched:
            return []
        blob = " ".join(searched).lower()
        return sorted(
            {
                phrase
                for facet in facets
                for phrase in _PHRASE_RE.findall(str(facet["query"]))
                if phrase.lower() not in blob
            },
        )

    async def _build_spec(
        self, panel: str, counted: list[tuple[str, Any]], claim: str,
    ) -> ChartSpecDTO:
        # Before the dispatch, not after it: by the time stance has built a spec
        # it has already refetched the core records and spent the classifier
        # call, and a thin set was never going to be drawn.
        matched = max(len(_deduped_records(counted)), *(c.total for _n, c in counted))
        floor = _MIN_RECORDS[panel]
        if matched < floor:
            thin_msg = (
                f"Only {_plural(matched, 'paper')} matched, under the {floor} a "
                f"{panel.replace('_', ' ')} panel needs to mean anything — a chart of "
                "that is a picture of the paper list, not of the literature. Broaden "
                "the facet query, or answer without the panel."
            )
            raise _PanelRefusedError(thin_msg)

        if panel == "timeline":
            spec = self._timeline(counted)
        elif panel == "evidence_mix":
            spec = await self._evidence_mix(counted)
        elif panel == "stance":
            spec = await self._stance(counted, claim)
        else:
            spec = await self._landmarks(counted)
        if panel != "landmarks":
            _densify_years(spec)
        # An axis with no bars under it is worse than no chart: it reads as
        # "nothing was published", when it means nothing was counted.
        if not any(s.points for s in spec.series):
            no_points_msg = (
                "No papers matched, so there is nothing to draw. Answer without the panel."
            )
            raise _PanelRefusedError(no_points_msg)
        return spec

    async def _count_facets(
        self, facets: list[dict[str, Any]], *, per_year: bool = True,
    ) -> tuple[list[tuple[str, Any]], str | None]:
        """Fetch each facet's counts, or the readable summary for the first failure.

        ``per_year=False`` for every panel but the timeline: they draw their own
        series and only need each facet's total, so paying 38 requests a facet
        for per-year counts nobody reads is pure waste.
        """
        counted: list[tuple[str, Any]] = []
        for facet in facets:
            query = str(facet["query"])
            try:
                counted.append((
                    str(facet.get("name") or "Papers"),
                    await self._client.year_counts(query, per_year=per_year),
                ))
            except LiteratureQueryError as exc:
                return [], _rejected_summary(query, exc)
            except LiteratureSourceUnavailableError as exc:
                return [], _outage_summary(query, exc)
        return counted, None

    def _timeline(self, counted: list[tuple[str, Any]]) -> ChartSpecDTO:
        return ChartSpecDTO(
            panel="timeline",
            title="Papers published per year",
            x_label="Year",
            y_label="Papers",
            series=[
                ChartSeriesDTO(
                    name=name,
                    points=[(float(y), float(n)) for y, n in sorted(c.counts.items())],
                )
                for name, c in counted
            ],
            partial_x=float(datetime.now(UTC).year),
            source_query=" · ".join(c.query for _n, c in counted),
            footnote=_scope_footnote(counted),
        )

    async def _evidence_mix(self, counted: list[tuple[str, Any]]) -> ChartSpecDTO:
        """Record kind per year, from records when we have them and counts when not.

        The panel used to require every facet exhaustive, which meant it only
        drew for topics too narrow for anyone to wonder whether they were
        primary research. It was attempted three times in the live pass and
        drew zero times. Europe PMC filters on publication type server-side,
        so above the limit the same picture is three count-only sweeps.
        """
        if all(c.exhaustive for _n, c in counted):
            by_bucket: dict[str, dict[int, int]] = {}
            for hit in _deduped_records(counted):
                if hit.year is None:
                    continue
                bucket = bucket_pub_type("; ".join(hit.pub_types))
                by_bucket.setdefault(bucket, {})
                by_bucket[bucket][hit.year] = by_bucket[bucket].get(hit.year, 0) + 1
            mix_all_years = True
        else:
            by_bucket, mix_all_years = await self._mix_by_counting(counted)

        return ChartSpecDTO(
            panel="evidence_mix",
            title="Kind of record, per year",
            x_label="Year",
            y_label="Records",
            series=[
                ChartSeriesDTO(
                    name=bucket,
                    points=[(float(y), float(n)) for y, n in sorted(years.items())],
                )
                for bucket, years in sorted(by_bucket.items())
            ],
            partial_x=float(datetime.now(UTC).year),
            source_query=" · ".join(c.query for _n, c in counted),
            footnote=_scope_footnote(counted, all_years=mix_all_years),
        )

    async def _mix_by_counting(
        self, counted: list[tuple[str, Any]],
    ) -> tuple[dict[str, dict[int, int]], bool]:
        """One per-year sweep per bucket, over the facets merged server-side.

        Merged with OR rather than summed per facet: facets overlap by
        construction, and summing their counts would double the shared papers.
        """
        merged = " OR ".join(f"({c.query})" for _n, c in counted)
        by_bucket: dict[str, dict[int, int]] = {}
        all_years = True
        for label, clause in _MIX_BUCKETS:
            try:
                bucket = await self._client.year_counts(f"({merged}) {clause}")
            except LiteratureQueryError as exc:
                raise _PanelRefusedError(_rejected_summary(merged, exc)) from exc
            except LiteratureSourceUnavailableError as exc:
                raise _PanelRefusedError(_outage_summary(merged, exc)) from exc
            if bucket.counts:
                by_bucket[label] = dict(bucket.counts)
            all_years = all_years and bucket.exhaustive
        return by_bucket, all_years

    _LANDMARK_LIMIT = 40

    async def _landmarks(self, counted: list[tuple[str, Any]]) -> ChartSpecDTO:
        """The head of the citation distribution, named.

        Europe PMC sorts by citation count server-side, so this is one request
        whatever the match size — which is why the panel no longer requires an
        exhaustive fetch. That requirement was not a budget: it forced the model
        into queries narrow enough to fit under 1000, and those queries excluded
        the canonical papers the panel exists to surface. The measured case
        plotted metformin-mechanism papers while omitting Zhou 2001.

        Undated records are dropped before the slice, not after: taking the top
        forty and then filtering silently returned a shorter chart.
        """
        merged = " OR ".join(f"({c.query})" for _n, c in counted)
        try:
            records = await self._client.top_cited(merged, limit=self._LANDMARK_LIMIT * 2)
        except LiteratureQueryError as exc:
            raise _PanelRefusedError(_rejected_summary(merged, exc)) from exc
        except LiteratureSourceUnavailableError as exc:
            raise _PanelRefusedError(_outage_summary(merged, exc)) from exc

        dated = [r for r in records if r.year is not None][: self._LANDMARK_LIMIT]
        return ChartSpecDTO(
            panel="landmarks",
            title="Citations against year",
            x_label="Year",
            y_label="Citations",
            series=[
                ChartSeriesDTO(
                    name="Citations",
                    points=[(float(r.year), float(r.cited_by_count)) for r in dated],
                    # A panel whose stated purpose is "the reader needs the
                    # canonical papers" has to be able to name one. Without this
                    # the tooltip reads "Citations : 1490" over an anonymous dot.
                    labels=[r.title or r.external_id for r in dated],
                ),
            ],
            source_query=" · ".join(c.query for _n, c in counted),
            footnote=_scope_footnote(counted, all_years=True),
        )

    async def _stance(self, counted: list[tuple[str, Any]], claim: str) -> ChartSpecDTO:
        from infrastructure.chat.stance_classifier import STANCE_LABELS, classify_stance

        if not all(c.exhaustive for _n, c in counted):
            raise _PanelRefusedError(_TOO_MANY_MSG)
        counted_records = _deduped_records(counted)
        if not counted_records:
            no_records_msg = "No papers matched, so there is nothing to score for stance."
            raise _PanelRefusedError(no_records_msg)
        if len(counted_records) > _STANCE_MAX_HITS:
            over_cap_msg = (
                f"Stance would need to read {len(counted_records)} papers, over the reading "
                f"budget of {_STANCE_MAX_HITS}. Narrow the SUBJECT, not the paper set: a "
                "facet naming one paper's title charts that paper alone. If the subject "
                f"will not go under {_STANCE_MAX_HITS} without naming individual papers, "
                "draw a timeline instead or answer without a panel."
            )
            raise _PanelRefusedError(over_cap_msg)

        hits = await self._core_records(counted)
        if not hits:
            no_abstracts_msg = (
                "No abstracts could be fetched for those papers, and stance is a "
                "judgement over abstracts. Answer without the panel."
            )
            raise _PanelRefusedError(no_abstracts_msg)

        try:
            verdicts = await classify_stance(self._stance_llm, claim, hits)
        except Exception as exc:
            log.warning("tool.literature.stance_failed", error=str(exc))
            failed_msg = f"Stance classification failed: {exc}. Answer without the panel."
            raise _PanelRefusedError(failed_msg) from exc
        if not verdicts:
            unusable_msg = "The stance classifier returned nothing usable. Answer without the panel."
            raise _PanelRefusedError(unusable_msg)

        by_id = {v.external_id: v for v in verdicts}
        # Undated hits are dropped, and must be dropped from the verdict list
        # too: a fragment under the chart for a paper that has no bar is an
        # entry the reader cannot find.
        dated = [h for h in hits if h.year is not None]
        stacks: dict[str, dict[int, int]] = {label: {} for label in STANCE_LABELS}
        for hit in dated:
            verdict = by_id.get(hit.external_id)
            label = verdict.label if verdict else "none"
            stacks[label][hit.year] = stacks[label].get(hit.year, 0) + 1

        return ChartSpecDTO(
            panel="stance",
            title=f"Papers on: {_truncate_claim(claim)}",
            x_label="Year",
            y_label="Papers",
            series=[
                ChartSeriesDTO(
                    name=label,
                    points=[(float(y), float(n)) for y, n in sorted(years.items())],
                )
                for label, years in stacks.items()
                if years
            ],
            partial_x=float(datetime.now(UTC).year),
            source_query=" · ".join(c.query for _n, c in counted),
            # A stance verdict is a judgement, and the reader has to be able to
            # overrule it. Without the fragment the chart is an assertion.
            # Joined by id, the way the bars are. The two agreed only because
            # classify_stance happens to rebuild one verdict per hit in order.
            notes=[
                f"{hit.year} · {v.label} · {hit.title[:80]} — “{v.evidence}”"
                for hit in dated
                if (v := by_id.get(hit.external_id)) is not None and v.evidence
            ][:60],
            footnote="All years.",
        )

    async def _core_records(self, counted: list[tuple[str, Any]]) -> list[Any]:
        """The same papers again, as core records — the only ones with abstracts.

        ``year_counts`` uses ``resultType=lite``, which carries no abstractText
        at all. Classifying its records scored titles against a prompt that
        demands a verbatim abstract quote, so every verdict was decided by a
        title and most evidence strings came back empty.
        """
        by_id: dict[str, Any] = {}
        for _name, c in counted:
            try:
                fetched = await self._client.search_or_raise(c.query, limit=_STANCE_MAX_HITS)
            except LiteratureQueryError as exc:
                raise _PanelRefusedError(_rejected_summary(c.query, exc)) from exc
            except LiteratureSourceUnavailableError as exc:
                raise _PanelRefusedError(_outage_summary(c.query, exc)) from exc
            for hit in fetched:
                by_id.setdefault((hit.source, hit.external_id), hit)
        return list(by_id.values())


def _stance_shape(spec: ChartSpecDTO) -> str:
    """The stance split in one line: the counts, and when the field turned.

    Shape only. The per-year series is on the chart the reader can see, and a
    model handed the whole series restates it as if it had read the papers.
    """
    from infrastructure.chat.stance_classifier import STANCE_LABELS

    totals = {s.name: int(sum(n for _y, n in s.points)) for s in spec.series}
    parts = ", ".join(f"{label} {totals[label]}" for label in STANCE_LABELS if label in totals)
    refutes = next((s for s in spec.series if s.name == "refutes" and s.points), None)
    turned = f"; first refutes {int(min(y for y, _n in refutes.points))}" if refutes else ""
    return f"- Stance: {parts}{turned}."


def _summarise(panel: str, counted: list[tuple[str, Any]], spec: ChartSpecDTO) -> str:
    """What the model reads: the shape, never the series.

    Chart payloads never enter conversation history — history is the prose,
    truncated to 500 characters. So this has to be short enough that the model's
    sentence about the chart survives, and shaped enough that the sentence is
    worth having.
    """
    this_year = datetime.now(UTC).year
    lines = [f"A {panel.replace('_', ' ')} panel was drawn for the reader."]
    for name, c in counted:
        years = sorted(c.counts)
        if not years:
            # No per-year counts: either nothing matched, or this panel asked
            # for the total alone. Saying a span here would invent one.
            lines.append(
                f"- {name}: {c.total:,} papers." if c.total else f"- {name}: no papers matched.",
            )
            continue
        # Anchored on today, not on years[-1]: a field whose last paper was
        # 2015 otherwise reports twelve papers "in the last five years".
        recent = sum(c.counts[y] for y in years if y >= this_year - 4)
        # ``total`` is the whole match; ``counts`` starts at 1990 in the
        # non-exhaustive regime, and for an old field that is a third of the
        # papers. Two numbers for two populations, never one sentence claiming
        # the total spans the counted years.
        span = (
            f"{years[0]}–{years[-1]}"
            if c.exhaustive
            else f"{max(years[0], _COUNT_FLOOR_YEAR)}–{years[-1]}, counted from {_COUNT_FLOOR_YEAR}"
        )
        lines.append(
            f"- {name}: {c.total:,} papers matched; {span}; "
            f"{recent} since {this_year - 4}.",
        )
    if spec.panel == "stance":
        lines.append(_stance_shape(spec))
    if spec.panel == "landmarks":
        drawn = len(spec.series[0].points) if spec.series else 0
        lines.append(f"- The panel plots the {drawn} most-cited of those, not all of them.")
    lines.append(
        "Describe the shape in your answer. Do not restate these numbers as if "
        "you had read them in an abstract.",
    )
    return "\n".join(lines)
