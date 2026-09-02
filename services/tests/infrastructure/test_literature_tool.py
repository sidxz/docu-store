"""The literature tool, and the registry that must contain only it.

The interesting behaviour is not the search — it is that a paper which is not in
the corpus still becomes something the synthesis stage can cite, without ever
pretending to be a document in this workspace.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest

from infrastructure.chat.tools.literature_tools import SearchLiteratureTool
from infrastructure.chat.tools.retrieval_tools import ToolRegistry
from infrastructure.literature.europe_pmc import LiteratureHit, parse_hit

FIXTURE = Path(__file__).parent.parent / "fixtures" / "europe_pmc_search_core.json"


@pytest.fixture
def hits() -> list[LiteratureHit]:
    records = json.loads(FIXTURE.read_text())["resultList"]["result"]
    return [parse_hit(r) for r in records]


class FakeClient:
    def __init__(self, hits: list[LiteratureHit]) -> None:
        self._hits = hits
        self.queries: list[str] = []

    async def search(self, query: str, *, limit: int = 25) -> list[LiteratureHit]:
        self.queries.append(query)
        return self._hits[:limit]


async def _run(client: FakeClient, **args):  # noqa: ANN003, ANN202
    return await SearchLiteratureTool(client).execute(args, uuid4(), None)


async def test_papers_become_citable_without_pretending_to_be_documents(hits):
    results, summary, events = await _run(FakeClient(hits), query='TITLE_ABS:"Pks13"')

    assert len(results) == len(hits)
    first = results[0]
    assert first.source_type == "literature"
    assert first.external_url == hits[0].url
    # Stable and derived from the paper's own identity, so the same paper is the
    # same id on every search -- and so it lines up if it is ever ingested.
    assert first.artifact_id == uuid5(NAMESPACE_URL, hits[0].url)
    assert summary
    assert events[0].type == "literature_results"


async def test_the_cards_keep_relevance_order_and_the_ingest_verdict(hits):
    _, _, events = await _run(FakeClient(hits), query="x")
    cards = events[0].literature_results

    assert [c["external_id"] for c in cards] == [h.external_id for h in hits], (
        "cards must stay in Europe PMC's relevance order: sorting by ingestability "
        "would systematically bury the most relevant med-chem papers"
    )
    nd = next(c for c in cards if c["licence"] == "cc by-nc-nd")
    assert nd["is_ingestable"] is False
    assert "derivative" in nd["ingest_blocker"]


async def test_the_summary_says_how_much_is_out_of_reach(hits):
    """The model has to be able to tell the user, so it has to be told."""
    _, summary, _ = await _run(FakeClient(hits), query="x")
    ingestable = sum(1 for h in hits if h.is_ingestable)
    assert f"{ingestable} can be added" in summary
    assert f"{len(hits) - ingestable} are abstract-and-link only" in summary


async def test_an_empty_query_does_not_reach_europe_pmc():
    client = FakeClient([])
    results, summary, events = await _run(client, query="   ")
    assert (results, events) == ([], [])
    assert client.queries == []
    assert "needs a query" in summary


async def test_the_tool_description_teaches_the_syntax_that_matters():
    """Because the lazy query looks better than the good one.

    A bare question matches full text, which only open papers have, so it
    returns what is open rather than what is relevant -- with every result
    showing an Add button. Nothing in the results reveals the mistake, so the
    description is the only place it can be prevented.
    """
    description = SearchLiteratureTool(FakeClient([])).definition.description
    assert "TITLE_ABS" in description
    assert "ABSTRACTS only" in description


class TestLiteratureRegistryIsExclusive:
    def _registry(self, **kwargs) -> ToolRegistry:  # noqa: ANN003
        return ToolRegistry(
            hierarchical_search=object(),
            summary_search=object(),
            page_read_model=object(),
            **kwargs,
        )

    def test_literature_mode_cannot_reach_the_corpus(self):
        registry = self._registry(literature_client=FakeClient([]), literature_only=True)
        names = [d.name for d in registry.definitions]
        assert "search_literature" in names
        assert "search_documents" not in names
        assert "search_summaries" not in names
        assert "get_page_content" not in names

    def test_ordinary_mode_has_no_literature_tool(self):
        names = [d.name for d in self._registry().definitions]
        assert "search_literature" not in names
        assert "search_documents" in names

    def test_a_literature_registry_without_a_client_refuses_to_exist(self):
        # Silently empty would mean a literature chat with no tools, which reads
        # as the model having nothing to say rather than as a wiring mistake.
        with pytest.raises(ValueError, match="needs a literature client"):
            self._registry(literature_only=True)
