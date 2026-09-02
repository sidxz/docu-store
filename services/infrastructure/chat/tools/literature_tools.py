"""Searching published literature from the chat, as a tool.

The tool description is doing real work here, so it is worth saying why. Europe
PMC's default search matches *full text* where it has it, and it only has full
text for open-access papers. A question handed over verbatim therefore returns
papers that are open before they are relevant: asking it "what are known
inhibitors of Pks13" returns 61 results, every one of them addable to a library,
and the top of the list is a review of tuberculosis treatment and a paper about
an assay artifact. The same question as ``TITLE_ABS:"Pks13" AND
TITLE_ABS:"inhibitor"`` returns 19, almost all of them genuinely about Pks13
inhibitors, and most of them paywalled.

That is the trap: the lazy query looks better than the good one, because its
results are all green buttons. So the description below teaches the field syntax
rather than leaving the model to guess, and nothing downstream sorts or filters
by whether a result can be ingested.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, UUID, uuid5

import structlog

from application.dtos.chat_dtos import AgentEvent
from application.ports.tool_calling_llm import ToolDefinition
from infrastructure.chat.models import RetrievalResult
from infrastructure.literature.europe_pmc import LiteratureSourceUnavailableError

if TYPE_CHECKING:
    from infrastructure.literature.europe_pmc import EuropePmcClient, LiteratureHit

log = structlog.get_logger()

SEARCH_LITERATURE_DEF = ToolDefinition(
    name="search_literature",
    description=(
        "Search published scientific literature on Europe PMC (48M records, all of "
        "biomedicine). Use this to find papers that are NOT yet in this workspace.\n\n"
        "Write a FIELDED query, not the user's question. A bare question matches full "
        "text, which exists only for open-access papers, so it silently returns "
        "whatever is open rather than whatever is relevant.\n\n"
        "Syntax:\n"
        '  TITLE_ABS:"term"     match title or abstract — prefer this for entities\n'
        "  AND / OR / NOT       combine\n"
        "  PUB_YEAR:[2020 TO 2026]\n"
        '  AUTH:"Surname I"\n'
        '  PUB_TYPE:"Retracted Publication"   also "Review", "Clinical Trial"\n\n'
        "Examples:\n"
        '  known inhibitors of Pks13  ->  TITLE_ABS:"Pks13" AND TITLE_ABS:"inhibitor"\n'
        '  recent InhA SAR work       ->  TITLE_ABS:"InhA" AND PUB_YEAR:[2022 TO 2026]\n'
        '  benzothiazinones for TB    ->  TITLE_ABS:"benzothiazinone" AND '
        'TITLE_ABS:"tuberculosis"\n\n'
        "If a fielded query genuinely returns 0 results, retry once with the bare "
        "terms. If it returns SEARCH FAILED — Europe PMC unreachable — that is an "
        "outage, not an empty result: retry the same fielded query, never a "
        "broader one.\n\n"
        "You see titles and ABSTRACTS only, never full text. Say what the abstracts "
        "support and no more. Many results will be paywalled; report them anyway — "
        "they are usually the most relevant, and the user can still read them at the "
        "publisher."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Europe PMC query, fielded where possible",
            },
            "limit": {
                "type": "integer",
                "description": "Results to return (default 20, max 50)",
            },
        },
        "required": ["query"],
    },
)


def _synthetic_artifact_id(hit: LiteratureHit) -> UUID:
    """A stable id for a paper that has no artifact.

    Derived from the DOI so it is the same id every time, and so it lines up
    with nothing else by accident. Nothing is stored under it — the client is
    told ``source_type: "literature"`` and sends the reader to the DOI instead.
    """
    return uuid5(NAMESPACE_URL, hit.url)


class SearchLiteratureTool:
    """Wraps Europe PMC search as an agent tool."""

    def __init__(self, client: EuropePmcClient) -> None:
        self._client = client

    @property
    def definition(self) -> ToolDefinition:
        return SEARCH_LITERATURE_DEF

    async def execute(
        self,
        args: dict[str, Any],
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
    ) -> tuple[list[RetrievalResult], str, list[AgentEvent]]:
        """Search, and hand back results the synthesis stage can cite.

        workspace_id and allowed_artifact_ids are ignored on purpose: published
        literature is not scoped to a tenant, and nothing here reads workspace
        state. They stay in the signature because the registry calls every tool
        the same way.
        """
        query = (args.get("query") or "").strip()
        limit = min(int(args.get("limit") or 20), 50)
        if not query:
            return [], "search_literature needs a query.", []

        try:
            hits = await self._client.search_or_raise(query, limit=limit)
        except LiteratureSourceUnavailableError as exc:
            log.warning("tool.literature.source_unavailable", query=query, error=str(exc))
            return [], _outage_summary(query, exc), []
        if not hits:
            return [], f"No Europe PMC results for: {query}", []

        results = [
            RetrievalResult(
                source_type="literature",
                artifact_id=_synthetic_artifact_id(h),
                artifact_title=h.title,
                authors=[a.strip() for a in (h.authors or "").split(",") if a.strip()],
                presentation_date=str(h.year) if h.year else None,
                expanded_text=h.abstract or h.title,
                matched_text=h.abstract or h.title,
                similarity_score=1.0,  # Europe PMC ranks; it does not score
                query_source="tool_literature",
                external_url=h.url,
            )
            for h in hits
        ]

        ingestable = sum(1 for h in hits if h.is_ingestable)
        log.info(
            "tool.literature.searched",
            query=query,
            hits=len(hits),
            ingestable=ingestable,
        )
        return results, _summarise(hits, query, ingestable), [_hits_event(hits)]


def _outage_summary(query: str, exc: Exception) -> str:
    """What the model reads when the source is down, not empty.

    The two cases are indistinguishable if both say "nothing came back", and the
    tool description tells the model to broaden on nothing. Broadening drops the
    fielded query for a bare one, which matches full text and so returns whatever
    is open rather than whatever is relevant.
    """
    return (
        f"SEARCH FAILED — Europe PMC is unreachable ({exc}). "
        f"The query `{query}` was NOT evaluated. This is a source outage, not an "
        "empty result. Do not broaden the query and do not drop the fielded "
        "syntax; the same query may work on a later attempt. If every search in "
        "this turn fails, tell the user that the literature source is currently "
        "unavailable and do not answer from your own knowledge."
    )


def _summarise(hits: list[LiteratureHit], query: str, ingestable: int) -> str:
    """What the model reads. Abstracts, and an honest note about the rest."""
    lines = [
        f"{len(hits)} Europe PMC results for `{query}` "
        f"({ingestable} can be added to the library, {len(hits) - ingestable} are "
        f"abstract-and-link only):",
        "",
    ]
    for i, h in enumerate(hits, start=1):
        where = " · ".join(p for p in (h.journal, str(h.year) if h.year else None) if p)
        lines.append(f"[{i}] {h.title}")
        if where:
            lines.append(f"    {where}")
        if h.abstract:
            lines.append(f"    {h.abstract[:900]}")
        lines.append("")
    return "\n".join(lines)


def _hits_event(hits: list[LiteratureHit]) -> AgentEvent:
    """The result cards. Relevance order, untouched — see the module docstring."""
    return AgentEvent(
        type="literature_results",
        literature_results=[
            {
                "external_id": h.external_id,
                "source": h.source,
                "title": h.title,
                "doi": h.doi,
                "pmcid": h.pmcid,
                "abstract": h.abstract,
                "journal": h.journal,
                "year": h.year,
                "authors": h.authors,
                "licence": h.licence,
                "is_open_access": h.is_open_access,
                "url": h.url,
                "is_ingestable": h.is_ingestable,
                "ingest_blocker": h.ingest_blocker(),
            }
            for h in hits
        ],
    )
