import asyncio
from types import SimpleNamespace
from uuid import uuid4

from application.services.compound_activity_query import CompoundActivityQuery


def _tm(entity_type, tag, bioactivities=None, synonyms=None):
    params = {}
    if bioactivities is not None:
        params["bioactivities"] = bioactivities
    if synonyms is not None:
        params["synonyms"] = synonyms
    return SimpleNamespace(entity_type=entity_type, tag=tag, additional_model_params=params)


def _page(page_id, index, artifact_id, tag_mentions):
    return SimpleNamespace(
        page_id=page_id, index=index, artifact_id=artifact_id, tag_mentions=tag_mentions,
    )


class FakeTagDict:
    """Returns artifact ids per entity_type so target intersection is exercised."""

    def __init__(self, by_type):
        self._by_type = by_type

    async def get_artifact_ids_for_tag(self, tag, entity_type, workspace_id):
        return self._by_type.get(entity_type, [])


class FakePages:
    """Filters to the requested artifact ids (so target narrowing actually bites)."""

    def __init__(self, pages):
        self._pages = pages

    async def get_pages_by_artifact_ids(self, ids, workspace_id):
        idset = set(ids)
        return [p for p in self._pages if p.artifact_id in idset]


class FakeArtifacts:
    async def get_artifact_by_id(self, artifact_id, workspace_id):
        return SimpleNamespace(title_mention=SimpleNamespace(title="Deck A"), source_filename="a.pdf")


def _make(by_type, pages):
    return CompoundActivityQuery(
        tag_dictionary=FakeTagDict(by_type),
        page_read_model=FakePages(pages),
        artifact_read_model=FakeArtifacts(),
    )


def test_collect_dedupes_bioactivities_and_keeps_all_refs():
    aid = uuid4()
    bio = [{"assay_type": "MIC", "value": "0.5", "unit": "uM", "raw_text": "x"}]
    q = _make(
        {"compound_name": [str(aid)]},
        pages=[
            _page(uuid4(), 1, aid, [_tm("compound_name", "CMX410", bioactivities=bio, synonyms="foo, bar")]),
            _page(uuid4(), 2, aid, [_tm("compound_name", "CMX410", bioactivities=bio)]),
        ],
    )
    bios, syn, refs = asyncio.run(q.collect("CMX410", uuid4(), None))
    assert [(b.assay_type, b.value, b.unit) for b in bios] == [("MIC", "0.5", "uM")]
    assert syn == ["bar", "foo"]
    assert len(refs) == 2  # both pages referenced, bio deduped to one
    assert refs[0].artifact_title == "Deck A"


def test_collect_target_intersection_narrows_artifacts():
    a, b = uuid4(), uuid4()
    pages = [
        _page(uuid4(), 1, a, [_tm("compound_name", "CMX410",
                                  bioactivities=[{"assay_type": "MIC", "value": "1", "unit": "uM"}])]),
        _page(uuid4(), 2, b, [_tm("compound_name", "CMX410",
                                  bioactivities=[{"assay_type": "IC50", "value": "9", "unit": "nM"}])]),
    ]
    by_type = {"compound_name": [str(a), str(b)], "target": [str(a)]}

    # No target → both artifacts contribute
    bios_all, _, refs_all = asyncio.run(_make(by_type, pages).collect("CMX410", uuid4(), None))
    assert {b.assay_type for b in bios_all} == {"MIC", "IC50"}
    assert len(refs_all) == 2

    # target=PknB → intersect to artifact A only
    bios_t, _, refs_t = asyncio.run(_make(by_type, pages).collect("CMX410", uuid4(), None, target="PknB"))
    assert [b.assay_type for b in bios_t] == ["MIC"]
    assert [r.artifact_id for r in refs_t] == [a]


def test_collect_target_gene_name_fallback():
    a, b = uuid4(), uuid4()
    pages = [
        _page(uuid4(), 1, a, [_tm("compound_name", "CMX410",
                                  bioactivities=[{"assay_type": "MIC", "value": "1"}])]),
        _page(uuid4(), 2, b, [_tm("compound_name", "CMX410",
                                  bioactivities=[{"assay_type": "IC50", "value": "9"}])]),
    ]
    # target has no "target" hits → falls back to gene_name (which lists only A)
    by_type = {"compound_name": [str(a), str(b)], "gene_name": [str(a)]}
    bios, _, refs = asyncio.run(_make(by_type, pages).collect("CMX410", uuid4(), None, target="pknB"))
    assert [b.assay_type for b in bios] == ["MIC"]
    assert [r.artifact_id for r in refs] == [a]


def test_collect_empty_for_unknown_compound():
    q = _make({}, pages=[])
    bios, syn, refs = asyncio.run(q.collect("NOPE", uuid4(), None))
    assert bios == [] and syn == [] and refs == []


def test_collect_acl_filters_out_non_allowed_artifacts():
    aid = uuid4()
    q = _make(
        {"compound_name": [str(aid)]},
        pages=[_page(uuid4(), 1, aid, [_tm("compound_name", "CMX410",
                                           bioactivities=[{"assay_type": "x", "value": "1"}])])],
    )
    bios, _, refs = asyncio.run(q.collect("CMX410", uuid4(), [uuid4()]))  # allowed excludes aid
    assert bios == [] and refs == []


def test_collect_empty_allowed_list_fails_closed():
    # allowed_artifact_ids == [] means "no accessible artifacts", NOT "no filter".
    # Regression guard: a truthy check ([] is falsy) would leak the whole workspace.
    aid = uuid4()
    q = _make(
        {"compound_name": [str(aid)]},
        pages=[_page(uuid4(), 1, aid, [_tm("compound_name", "CMX410",
                                           bioactivities=[{"assay_type": "x", "value": "1"}])])],
    )
    bios, _, refs = asyncio.run(q.collect("CMX410", uuid4(), []))
    assert bios == [] and refs == []
