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
        "Call this AFTER searching, at most twice in a turn, and only when a panel "
        "genuinely answers the question. Most questions need none.\n\n"
        "Panels:\n"
        "  timeline    — volume over time. For 'is this growing', 'what is new', "
        "and any question comparing eras. Each facet becomes a series, so a "
        "question with two competing sides is best plotted as two facets.\n"
        "  evidence_mix— research articles vs reviews vs preprints vs patents "
        "over time. For 'is this primary work', and it exposes industrial "
        "programmes, which show up as patent clusters years before papers.\n"
        "  landmarks   — citations against year. For settled knowledge, where a "
        "timeline is noise and the reader needs the canonical papers.\n"
        "  stance      — how each paper stands on a CLAIM, over time. Only when the "
        "question contains a claim to adjudicate. Requires 'claim'.\n\n"
        'Pass facets as [{"name": "short label", "query": "a fielded Europe '
        'PMC query"}]. Use the SAME fielded queries you searched with — a '
        "broadened query charts a different set of papers than the one the reader "
        "sees listed.\n\n"
        "Examples:\n"
        '  do MmpL3 inhibitors disrupt PMF or bind directly  ->  timeline, facets '
        '[{"name":"PMF","query":"TITLE_ABS:\\"MmpL3\\" AND TITLE_ABS:\\"proton '
        'motive force\\""}, {"name":"Structure","query":"TITLE_ABS:\\"MmpL3\\" AND '
        'TITLE_ABS:\\"structure\\""}]\n'
        "  what is isoniazid's mechanism of action  ->  landmarks\n"
        "  how did BTZ resistance change after 2020  ->  timeline"
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
                "description": "One series per facet. Usually one; two when the question has two sides.",
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

        spec = await self._build_spec(panel, counted, claim)
        if spec is None:
            return (
                [],
                "That panel needs the individual records, and this query matches "
                "too many to fetch them. Narrow the query, or use a timeline.",
                [],
            )

        claim_panel_slot()
        log.info(
            "tool.literature.plotted",
            panel=panel,
            facets=len(counted),
            total=sum(c.total for _n, c in counted),
        )
        return [], _summarise(panel, counted), [
            AgentEvent(
                type="structured_block",
                block=ContentBlockDTO(type="chart", chart=spec),
            ),
        ]

    def _validate_args(
        self, panel: str, facets: list[dict[str, Any]], claim: str,
    ) -> str | None:
        """The readable refusal for a bad call, or None when it may proceed."""
        if not facets:
            return "plot_literature needs at least one facet with a query."
        if panel not in {"timeline", "evidence_mix", "landmarks", "stance"}:
            return f"Unknown panel '{panel}'. Use timeline, evidence_mix, landmarks or stance."
        if panel == "stance" and not claim:
            return "panel=stance needs a 'claim': the assertion to score papers against."
        if panel == "stance" and self._stance_llm is None:
            return "Stance classification is not configured on this deployment."
        return None

    async def _build_spec(
        self, panel: str, counted: list[tuple[str, Any]], claim: str,
    ) -> ChartSpecDTO | None:
        if panel == "timeline":
            return self._timeline(counted)
        if panel == "evidence_mix":
            return self._evidence_mix(counted)
        if panel == "stance":
            return await self._stance(counted, claim)
        return self._landmarks(counted)

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
            footnote="Counts are the whole Europe PMC match, not the papers retrieved.",
        )

    def _evidence_mix(self, counted: list[tuple[str, Any]]) -> ChartSpecDTO | None:
        # Needs the records themselves, which only exist below the exhaustive
        # limit. Above it, only counts were fetched.
        if not all(c.exhaustive for _n, c in counted):
            return None
        records = [r for _n, c in counted for r in c.records]

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

    def _landmarks(self, counted: list[tuple[str, Any]]) -> ChartSpecDTO | None:
        if not all(c.exhaustive for _n, c in counted):
            return None
        records = [r for _n, c in counted for r in c.records]
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
            footnote=(
                "Citation counts favour older papers mechanically. Use this to find "
                "what everyone cites, never to rank quality."
            ),
        )

    async def _stance(self, counted: list[tuple[str, Any]], claim: str) -> ChartSpecDTO | None:
        from infrastructure.chat.stance_classifier import STANCE_LABELS, classify_stance

        if not all(c.exhaustive for _n, c in counted):
            return None
        hits = [r for _n, c in counted for r in c.records]
        if not hits:
            return None

        verdicts = await classify_stance(self._stance_llm, claim, hits)
        if not verdicts:
            return None

        by_id = {v.external_id: v.label for v in verdicts}
        stacks: dict[str, dict[int, int]] = {label: {} for label in STANCE_LABELS}
        for hit in hits:
            if hit.year is None:
                continue
            label = by_id.get(hit.external_id, "none")
            stacks[label][hit.year] = stacks[label].get(hit.year, 0) + 1

        return ChartSpecDTO(
            panel="stance",
            title=f"Papers on: {claim}",
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
            footnote=(
                "Each paper scored against the claim, not for sentiment. "
                "Most papers take no position, which is expected."
            ),
        )


def _summarise(panel: str, counted: list[tuple[str, Any]]) -> str:
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
    lines.append(
        "Describe the shape in your answer. Do not restate these numbers as if "
        "you had read them in an abstract.",
    )
    return "\n".join(lines)
