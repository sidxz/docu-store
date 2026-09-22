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

    # (a) markdown table: what each value was measured against (protein target, strain)
    # and the page it was read on (1-based, as the UI numbers pages)
    assert "| Compound | Target | Strain | Assay | Value | Page |" in r.expanded_text
    assert "| CMX410 |  |  | MIC | 0.5 uM | 2 |" in r.expanded_text

    # summary string shape preserved
    assert summary == "Bioactivity search for 'CMX410': 1 data points from 1 documents."


def test_tool_cites_each_value_to_the_deck_it_was_read_in():
    """Values from two decks used to share one result, cited to the first deck."""
    deck_a, deck_b = uuid4(), uuid4()
    ev71 = {"assay_type": "IC50", "value": "13.3", "unit": "µM", "assay": "Vero", "strain": "EV71"}
    vsv = {"assay_type": "EC50", "value": "17", "unit": "µM", "assay": "HeLa", "strain": "VSV"}
    activity = CompoundActivityQuery(
        tag_dictionary=FakeTagDict([str(deck_a), str(deck_b)]),
        page_read_model=FakePages([
            _page(deck_a, [_tm("compound_name", "CHEMBL1643", bioactivities=[ev71])]),
            _page(deck_b, [_tm("compound_name", "CHEMBL1643", bioactivities=[vsv])]),
        ]),
        artifact_read_model=FakeArtifacts(),
    )
    tool = SearchStructuredBioactivityTool(activity_query=activity, artifact_read_model=None)
    results, _, _ = asyncio.run(tool.execute({"compound_name": "CHEMBL1643"}, uuid4(), None))

    assert [r.artifact_id for r in results] == [deck_a, deck_b]
    assert "| CHEMBL1643 |  | EV71 | IC50 (Vero) | 13.3 µM | 2 |" in results[0].expanded_text
    assert "VSV" not in results[0].expanded_text
    assert "| CHEMBL1643 |  | VSV | EC50 (HeLa) | 17 µM | 2 |" in results[1].expanded_text
    # Molecule cards read the first result's list (agentic_retrieval step 1b): every row
    # rides there, so splitting the table per deck costs the card nothing.
    assert [b.value for b in results[0].bioactivities] == ["13.3", "17"]
    assert results[1].bioactivities is None


def test_tool_shows_the_target_and_the_partner():
    """0.7.0 files the protein under `target` and a partner drug under `combination`: a
    Ki against hCA XII, and an MRC measured with meropenem, not the compound alone."""
    aid = uuid4()
    pages = [_page(aid, [_tm("compound_name", "13d", bioactivities=[
        {"assay_type": "Ki", "value": "0.6", "unit": "nM", "target": "hCA XII"},
        {"assay_type": "MRC", "value": "1", "unit": "µg/mL", "strain": "MRSA", "combination": "meropenem"},
    ])])]
    results, _, _ = asyncio.run(_tool(aid, pages).execute({"compound_name": "13d"}, uuid4(), None))

    assert "| 13d | hCA XII |  | Ki | 0.6 nM | 2 |" in results[0].expanded_text
    assert "| 13d |  | MRSA | MRC, with meropenem | 1 µg/mL | 2 |" in results[0].expanded_text


def test_tool_says_a_target_narrows_documents_not_rows():
    """Asked for ribavirin against RSV, the tool returned every ribavirin value without a
    word, so a SARS-CoV value was reported as the RSV one."""
    aid, other = uuid4(), uuid4()
    pages = [
        _page(aid, [_tm("compound_name", "ribavirin", bioactivities=[
            {"assay_type": "EC50", "value": "109.5", "unit": "µM", "assay": "SARS-CoV"},
        ])]),
        _page(other, [_tm("compound_name", "ribavirin", bioactivities=[
            {"assay_type": "IC50", "value": "80", "unit": "nM", "assay": "HEp-2"},
        ])]),
    ]
    activity = CompoundActivityQuery(
        tag_dictionary=FakeTagDict([str(aid), str(other)]),
        page_read_model=FakePages(pages),
        artifact_read_model=FakeArtifacts(),
    )
    tool = SearchStructuredBioactivityTool(activity_query=activity, artifact_read_model=None)

    results, summary, _ = asyncio.run(
        tool.execute({"compound_name": "ribavirin", "target_name": "RSV"}, uuid4(), None),
    )
    assert "'RSV' narrows which documents are searched, not which rows" in results[0].expanded_text
    assert "narrows documents, not rows" in summary
    # Once, not once per deck: tool output is exempt from the context cap and its budget
    # is reserved first, so every repeat is paid for out of the evidence it displaces.
    assert "narrows" not in results[1].expanded_text

    # NER's placeholder is no target at all
    results, summary, _ = asyncio.run(
        tool.execute({"compound_name": "ribavirin", "target_name": "None"}, uuid4(), None),
    )
    assert "narrows" not in results[0].expanded_text
    assert "narrows" not in summary


def test_tool_no_data_returns_empty_and_message():
    tool = _tool(uuid4(), pages=[])  # tag dict returns an id but no pages match → no refs
    results, summary, events = asyncio.run(
        tool.execute({"compound_name": "GHOST"}, uuid4(), None),
    )
    assert results == []
    assert "No accessible documents" in summary
    assert events == []
