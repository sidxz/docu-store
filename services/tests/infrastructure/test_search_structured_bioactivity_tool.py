import asyncio
from types import SimpleNamespace
from uuid import uuid4

from application.services.compound_activity_query import CompoundActivityQuery
from infrastructure.chat.tools.retrieval_tools import SearchStructuredBioactivityTool


def _tm(entity_type, tag, bioactivities=None):
    params = {"bioactivities": bioactivities} if bioactivities is not None else {}
    return SimpleNamespace(entity_type=entity_type, tag=tag, additional_model_params=params)


def _page(artifact_id, tag_mentions):
    return SimpleNamespace(
        page_id=uuid4(), index=1, artifact_id=artifact_id, tag_mentions=tag_mentions,
    )


class FakeTagDict:
    def __init__(self, ids):
        self._ids = ids

    async def get_artifact_ids_for_tag(self, tag, entity_type, workspace_id):
        return self._ids


class FakePages:
    def __init__(self, pages):
        self._pages = pages

    async def get_pages_by_artifact_ids(self, ids, workspace_id):
        return self._pages


class FakeArtifacts:
    async def get_artifact_by_id(self, artifact_id, workspace_id):
        return SimpleNamespace(title_mention=SimpleNamespace(title="Deck A"), source_filename="a.pdf")


def _tool(aid, pages):
    activity = CompoundActivityQuery(
        tag_dictionary=FakeTagDict([str(aid)]),
        page_read_model=FakePages(pages),
        artifact_read_model=FakeArtifacts(),
    )
    return SearchStructuredBioactivityTool(activity_query=activity, artifact_read_model=None)


def test_tool_sets_structured_bioactivities_and_returns_markdown_table():
    aid = uuid4()
    tool = _tool(
        aid,
        pages=[_page(aid, [
            _tm("compound_name", "CMX410",
                bioactivities=[{"assay_type": "MIC", "value": "0.5", "unit": "uM", "raw_text": "MIC 0.5 uM"}]),
        ])],
    )
    results, summary, events = asyncio.run(
        tool.execute({"compound_name": "CMX410"}, uuid4(), None),
    )

    assert events == []
    assert results, "expected a synthetic table-carrying result"
    r = results[0]

    # (b) structured bioactivities ride on the result → feeds F3 molecule block
    assert r.bioactivities is not None
    assert [(b.assay_type, b.value, b.unit) for b in r.bioactivities] == [("MIC", "0.5", "uM")]

    # (a) markdown table preserved — header + a blank Target cell exactly as before
    assert "| Compound | Target | Assay | Value |" in r.expanded_text
    assert "| CMX410 |  | MIC | 0.5 uM |" in r.expanded_text

    # summary string shape preserved
    assert summary == "Bioactivity search for 'CMX410': 1 data points from 1 documents."


def test_tool_no_data_returns_empty_and_message():
    tool = _tool(uuid4(), pages=[])  # tag dict returns an id but no pages match → no refs
    results, summary, events = asyncio.run(
        tool.execute({"compound_name": "GHOST"}, uuid4(), None),
    )
    assert results == []
    assert "No accessible documents" in summary
    assert events == []
