import asyncio
from types import SimpleNamespace
from uuid import uuid4

from application.dtos.compound_dtos import CompoundProfileDTO
from application.use_cases.compound_profile_use_case import GetCompoundProfileUseCase


def _tm(entity_type, tag, bioactivities=None, synonyms=None):
    params = {}
    if bioactivities is not None:
        params["bioactivities"] = bioactivities
    if synonyms is not None:
        params["synonyms"] = synonyms
    return SimpleNamespace(entity_type=entity_type, tag=tag, additional_model_params=params)


def _page(page_id, index, artifact_id, tag_mentions):
    return SimpleNamespace(page_id=page_id, index=index, artifact_id=artifact_id, tag_mentions=tag_mentions)


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


class FakeCompounds:
    def __init__(self, results):
        self._results = results

    async def get_compounds_by_extracted_id(self, extracted_id, workspace_id, allowed_artifact_ids):
        return self._results


def _make(structures, tag_ids, pages):
    return GetCompoundProfileUseCase(
        tag_dictionary=FakeTagDict(tag_ids),
        page_read_model=FakePages(pages),
        artifact_read_model=FakeArtifacts(),
        compound_vector_store=FakeCompounds(structures),
    )


def test_profile_joins_structure_bioactivities_and_pages():
    aid = uuid4()
    pid = uuid4()
    uc = _make(
        structures=[SimpleNamespace(canonical_smiles="C", smiles="C", extracted_id="CMX410")],
        tag_ids=[str(aid)],
        pages=[_page(pid, 3, aid, [
            _tm("compound_name", "CMX410",
                bioactivities=[{"assay_type": "MIC", "value": "0.5", "unit": "uM", "raw_text": "MIC 0.5 uM"}],
                synonyms="foo, bar"),
        ])],
    )
    dto = asyncio.run(uc.execute("CMX410", uuid4(), None))
    assert isinstance(dto, CompoundProfileDTO)
    assert dto.has_structure is True
    assert dto.canonical_smiles == "C"
    assert dto.extracted_id == "CMX410"
    assert [(b.assay_type, b.value, b.unit) for b in dto.bioactivities] == [("MIC", "0.5", "uM")]
    assert dto.synonyms == ["bar", "foo"]
    assert [(r.page_index, str(r.artifact_id)) for r in dto.reference_pages] == [(3, str(aid))]


def test_profile_dedupes_bioactivities_across_pages():
    aid = uuid4()
    bio = [{"assay_type": "MIC", "value": "0.5", "unit": "uM", "raw_text": "x"}]
    uc = _make(
        structures=[],
        tag_ids=[str(aid)],
        pages=[
            _page(uuid4(), 1, aid, [_tm("compound_name", "CMX410", bioactivities=bio)]),
            _page(uuid4(), 2, aid, [_tm("compound_name", "CMX410", bioactivities=bio)]),
        ],
    )
    dto = asyncio.run(uc.execute("CMX410", uuid4(), None))
    assert dto.has_structure is False
    assert len(dto.bioactivities) == 1
    assert len(dto.reference_pages) == 2  # both pages referenced


def test_profile_empty_for_unknown_name():
    uc = _make(structures=[], tag_ids=[], pages=[])
    dto = asyncio.run(uc.execute("NOPE", uuid4(), None))
    assert dto.has_structure is False
    assert dto.bioactivities == []
    assert dto.reference_pages == []


def test_profile_acl_filters_out_non_allowed_artifacts():
    aid = uuid4()
    uc = _make(
        structures=[],
        tag_ids=[str(aid)],
        pages=[_page(uuid4(), 1, aid, [_tm("compound_name", "CMX410", bioactivities=[{"assay_type": "x", "value": "1"}])])],
    )
    # allowed list excludes aid → no data
    dto = asyncio.run(uc.execute("CMX410", uuid4(), [uuid4()]))
    assert dto.bioactivities == []
    assert dto.reference_pages == []
