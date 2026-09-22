import asyncio
from types import SimpleNamespace
from uuid import uuid4

from application.dtos.compound_dtos import CompoundProfileDTO
from application.services.compound_activity_query import CompoundActivityQuery
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
    activity = CompoundActivityQuery(
        tag_dictionary=FakeTagDict(tag_ids),
        page_read_model=FakePages(pages),
        artifact_read_model=FakeArtifacts(),
    )
    return GetCompoundProfileUseCase(
        activity_query=activity,
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


def test_profile_never_takes_a_structure_from_a_deck_that_labels_it_otherwise():
    """Deck B calls CHEMBL6109008 '12'; deck A calls it '8l' and separately draws an
    unrelated compound as '12'. Pooling both decks' labels and trying each against every
    deck put deck A's compound 12 on this profile. A label belongs to the deck that used it."""
    deck_a, deck_b = uuid4(), uuid4()

    class ByDeck:
        def __init__(self):
            self.calls = []

        async def get_compounds_by_extracted_id(self, extracted_id, workspace_id, allowed_artifact_ids):
            decks = list(allowed_artifact_ids or [])
            self.calls.append((extracted_id, decks))
            if extracted_id == "12" and deck_a in decks:  # deck A's unrelated compound 12
                return [SimpleNamespace(canonical_smiles="CCN", smiles="CCN", extracted_id="12")]
            if extracted_id == "8l" and deck_a in decks:
                return [SimpleNamespace(canonical_smiles="CCO", smiles="CCO", extracted_id="8l")]
            if extracted_id == "12" and deck_b in decks:
                return [SimpleNamespace(canonical_smiles="CCO", smiles="CCO", extracted_id="12")]
            return []

    store = ByDeck()
    pages = [
        _page(uuid4(), 5, deck_a, [_tm("compound_name", "CHEMBL6109008", synonyms="8l")]),
        _page(uuid4(), 2, deck_b, [_tm("compound_name", "CHEMBL6109008", synonyms="12")]),
    ]
    uc = GetCompoundProfileUseCase(
        activity_query=CompoundActivityQuery(
            tag_dictionary=FakeTagDict([str(deck_a), str(deck_b)]),
            page_read_model=FakePages(pages),
            artifact_read_model=FakeArtifacts(),
        ),
        compound_vector_store=store,
    )
    dto = asyncio.run(uc.execute("CHEMBL6109008", uuid4(), None))

    assert dto.canonical_smiles == "CCO", "deck A's compound 12 is not this compound"
    assert ("12", [deck_a]) not in store.calls
    assert ("12", [deck_a, deck_b]) not in store.calls


def test_profile_finds_the_structure_under_a_synonym_in_its_own_deck():
    """The card is CHEMBL6109008; CSER labelled the drawing with the deck's '8l'.
    Every deck has an 8l, so the synonym is only looked up where this compound is."""
    aid = uuid4()

    class ByLabel:
        def __init__(self):
            self.calls = []

        async def get_compounds_by_extracted_id(self, extracted_id, workspace_id, allowed_artifact_ids):
            self.calls.append((extracted_id, allowed_artifact_ids))
            if extracted_id == "8l":
                return [SimpleNamespace(canonical_smiles="CCO", smiles="CCO", extracted_id="8l")]
            return []

    store = ByLabel()
    uc = GetCompoundProfileUseCase(
        activity_query=CompoundActivityQuery(
            tag_dictionary=FakeTagDict([str(aid)]),
            page_read_model=FakePages(
                [_page(uuid4(), 5, aid, [_tm("compound_name", "CHEMBL6109008", synonyms="8l")])],
            ),
            artifact_read_model=FakeArtifacts(),
        ),
        compound_vector_store=store,
    )
    dto = asyncio.run(uc.execute("CHEMBL6109008", uuid4(), None))

    assert dto.has_structure is True
    assert dto.extracted_id == "8l"
    assert store.calls[-1] == ("8l", [aid])
