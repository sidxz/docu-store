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
    panel_budget_spent,
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
        "turn. The reader asked for a chart; pick the panel that fits the "
        "question's shape.\n\n"
        "Panels:\n"
        "  timeline    — volume over time. For 'is this growing', 'what is new', "
        "and for when the question asks how one thing gave way to another. Each "
        "facet becomes a series drawn across the whole span.\n"
        "  evidence_mix— research articles vs reviews vs preprints vs patents "
        "over time. For 'is this primary work', and it exposes industrial "
        "programmes, which show up as patent clusters years before papers.\n"
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

_TOO_MANY_MSG = (
    "That panel needs the individual records, and this query matches "
    "too many to fetch them. Narrow the query, or use a timeline."
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


def _timeline_footnote(counted: list[tuple[str, Any]]) -> str:
    """Where the counts come from, honestly, in each of the two regimes.

    Above the exhaustive limit the counts are per-year requests from ``since``
    (1990), so claiming "all years" would hide every paper before 1990 --
    thousands of them, for an established field.
    """
    if all(c.exhaustive for _n, c in counted):
        return "All years."
    return "From 1990 on."


def _truncate_claim(claim: str, limit: int = 120) -> str:
    """Truncate at the last space before ``limit`` chars, never mid-word."""
    if len(claim) <= limit:
        return claim
    cut = claim[:limit].rfind(" ")
    return f"{claim[: cut if cut > 0 else limit]}…"


def _deduped_records(counted: list[tuple[str, Any]]) -> list[Any]:
    """Every record across the facets, each once.

    Facets overlap by construction -- two sides of one question share papers --
    and an undeduped concatenation draws the shared ones twice.
    """
    return list({r.external_id: r for _n, c in counted for r in c.records}.values())


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

        counted, error_summary = await self._count_facets(facets)
        if error_summary is not None:
            return [], error_summary, []

        try:
            spec = await self._build_spec(panel, counted, claim)
        except _PanelRefusedError as exc:
            return [], str(exc), []

        claim_panel_slot()
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
        if any("pub_year" in str(f["query"]).lower() for f in facets):
            return (
                "Facet queries must not filter by year: the chart's x-axis is already the "
                "year, so a windowed query draws a series that stops where the filter "
                "does. Resend the same queries with the PUB_YEAR clause removed."
            )
        if panel not in {"timeline", "evidence_mix", "landmarks", "stance"}:
            return f"Unknown panel '{panel}'. Use timeline, evidence_mix, landmarks or stance."
        if panel == "stance" and not claim:
            return "panel=stance needs a 'claim': the assertion to score papers against."
        if panel == "stance" and self._stance_llm is None:
            return "Stance classification is not configured on this deployment."
        return None

    async def _build_spec(
        self, panel: str, counted: list[tuple[str, Any]], claim: str,
    ) -> ChartSpecDTO:
        if panel == "timeline":
            spec = self._timeline(counted)
        elif panel == "evidence_mix":
            spec = self._evidence_mix(counted)
        elif panel == "stance":
            spec = await self._stance(counted, claim)
        else:
            spec = self._landmarks(counted)
        # An axis with no bars under it is worse than no chart: it reads as
        # "nothing was published", when it means nothing was counted.
        if not any(s.points for s in spec.series):
            no_points_msg = (
                "No papers matched, so there is nothing to draw. Answer without the panel."
            )
            raise _PanelRefusedError(no_points_msg)
        return spec

    async def _count_facets(
        self, facets: list[dict[str, Any]],
    ) -> tuple[list[tuple[str, Any]], str | None]:
        """Fetch each facet's counts, or the readable summary for the first failure."""
        counted: list[tuple[str, Any]] = []
        for facet in facets:
            query = str(facet["query"])
            try:
                counted.append((str(facet.get("name") or "Papers"), await self._client.year_counts(query)))
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
            footnote=_timeline_footnote(counted),
        )

    def _evidence_mix(self, counted: list[tuple[str, Any]]) -> ChartSpecDTO:
        # Needs the records themselves, which only exist below the exhaustive
        # limit. Above it, only counts were fetched.
        if not all(c.exhaustive for _n, c in counted):
            raise _PanelRefusedError(_TOO_MANY_MSG)
        records = _deduped_records(counted)

        by_bucket: dict[str, dict[int, int]] = {}
        for hit in records:
            if hit.year is None:
                continue
            bucket = bucket_pub_type("; ".join(hit.pub_types))
            by_bucket.setdefault(bucket, {})
            by_bucket[bucket][hit.year] = by_bucket[bucket].get(hit.year, 0) + 1

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
        )

    def _landmarks(self, counted: list[tuple[str, Any]]) -> ChartSpecDTO:
        if not all(c.exhaustive for _n, c in counted):
            raise _PanelRefusedError(_TOO_MANY_MSG)
        records = _deduped_records(counted)
        top = sorted(records, key=lambda r: -r.cited_by_count)[:40]
        return ChartSpecDTO(
            panel="landmarks",
            title="Citations against year",
            x_label="Year",
            y_label="Citations",
            series=[
                ChartSeriesDTO(
                    name="Citations",
                    points=[
                        (float(r.year), float(r.cited_by_count))
                        for r in top
                        if r.year is not None
                    ],
                ),
            ],
            source_query=" · ".join(c.query for _n, c in counted),
            footnote="All years.",
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
                f"budget of {_STANCE_MAX_HITS}. Narrow the facet query and try again."
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

        by_id = {v.external_id: v.label for v in verdicts}
        stacks: dict[str, dict[int, int]] = {label: {} for label in STANCE_LABELS}
        for hit in hits:
            if hit.year is None:
                continue
            label = by_id.get(hit.external_id, "none")
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
            notes=[
                f"{hit.year} · {v.label} · {hit.title[:80]} — “{v.evidence}”"
                for hit, v in zip(hits, verdicts, strict=False)
                if v.label != "none" and v.evidence
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
                by_id.setdefault(hit.external_id, hit)
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
    lines = [f"A {panel.replace('_', ' ')} panel was drawn for the reader."]
    for name, c in counted:
        years = sorted(c.counts)
        if not years:
            lines.append(f"- {name}: no papers matched.")
            continue
        recent = sum(c.counts[y] for y in years if y >= years[-1] - 4)
        lines.append(
            f"- {name}: {c.total} papers, {years[0]}–{years[-1]}, "
            f"{recent} in the last five years.",
        )
    if spec.panel == "stance":
        lines.append(_stance_shape(spec))
    lines.append(
        "Describe the shape in your answer. Do not restate these numbers as if "
        "you had read them in an abstract.",
    )
    return "\n".join(lines)
