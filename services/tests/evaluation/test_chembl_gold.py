"""Checks for the ChEMBL-gold benchmark: normalisation, scoring, generation."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import pytest

from evaluation.chembl_gold import load_corpus, normalize_unit, strip_markup, structure_key
from evaluation.metrics import (
    abstention_score,
    context_pollution_by_docs,
    entity_retention,
    extract_values,
    value_match,
)
from evaluation.query_set import (
    EvalQuery,
    GoldDocRelevance,
    QuerySet,
    bind_query_set,
)

GOLD = Path(__file__).parents[2] / "evaluation" / "datasets" / "chembl_gold" / "gold" / "gold_corpus.json"


# --- unit normalisation -----------------------------------------------------

def test_molar_units_convert_to_nm():
    assert normalize_unit("uM", 1.0) == (1000.0, "nM", "molar")
    assert normalize_unit("nM", 40.0) == (40.0, "nM", "molar")
    assert normalize_unit("mM", 1.0) == (1e6, "nM", "molar")


def test_millimolar_and_millimetre_are_not_confused():
    """'mM' is millimolar; 'mm' is a zone-of-inhibition diameter."""
    assert normalize_unit("mM", 1.0)[1] == "nM"
    value, unit, dimension = normalize_unit("mm", 12.0)
    assert (value, unit, dimension) == (12.0, "mm", "other")


def test_mass_per_volume_spellings_agree():
    for spelling in ("ug.mL-1", "ug ml-1", "µg/mL", "ug/ml"):
        assert normalize_unit(spelling, 2.0) == (2.0, "ug.mL-1", "mass_vol")
    assert normalize_unit("ng.mL-1", 1000.0) == (1.0, "ug.mL-1", "mass_vol")


def test_unknown_units_pass_through_untouched():
    assert normalize_unit("deltalog10CFU", 3.0) == (3.0, "deltalog10CFU", "other")
    assert normalize_unit(None, 5.0) == (5.0, None, "none")


def test_strip_markup_removes_chembl_html():
    assert strip_markup("Inhibitors of <i>M. tuberculosis</i>") == "Inhibitors of M. tuberculosis"


# --- structure identity -----------------------------------------------------

def test_structure_key_ignores_counter_ions():
    """A hydrochloride salt and its free base are the same compound."""
    free_base = structure_key("CCN")
    salt = structure_key("CCN.Cl")
    assert free_base is not None
    assert free_base == salt


def test_structure_key_distinguishes_different_molecules():
    assert structure_key("CCN") != structure_key("CCCN")


def test_structure_key_survives_bad_smiles():
    assert structure_key("not-a-molecule") is None
    assert structure_key(None) is None


# --- answer scoring ---------------------------------------------------------

def test_value_match_across_units_in_same_dimension():
    """40 nM published as 0.04 µM is the same measurement."""
    assert value_match("The IC50 was 0.04 uM.", 40.0, "nM")["value_match"] == 1.0
    assert value_match("IC50 = 40 nM", 40.0, "nM")["value_match"] == 1.0


def test_value_match_rejects_wrong_dimension():
    """0.04 µg/mL is not 40 nM — no molecular weight, no cross-dimension match."""
    assert value_match("MIC of 0.04 ug/mL", 40.0, "nM")["value_match"] == 0.0


def test_value_match_rejects_different_value():
    assert value_match("IC50 = 400 nM", 40.0, "nM")["value_match"] == 0.0


def test_value_match_absorbs_rounding_only():
    assert value_match("IC50 = 40.2 nM", 40.0, "nM")["value_match"] == 1.0
    assert value_match("IC50 = 45 nM", 40.0, "nM")["value_match"] == 0.0


def test_value_match_tracks_censoring_relation():
    censored = value_match("MIC < 0.016 ug/mL", 0.016, "ug.mL-1", "<")
    assert censored == {"value_match": 1.0, "relation_match": 1.0}
    uncensored = value_match("MIC is 0.016 ug/mL", 0.016, "ug.mL-1", "<")
    assert uncensored["value_match"] == 1.0
    assert uncensored["relation_match"] == 0.0


def test_extract_values_finds_every_measurement_mentioned():
    values = extract_values("Compound 3 gave 12 nM and compound 4 gave 1.5 uM.")
    assert (12.0, "nM", "=") in values
    assert (1500.0, "nM", "=") in values


def test_abstention_scoring_separates_refusal_from_invention():
    assert abstention_score("The corpus does not contain this measurement.")["abstained"] == 1.0
    assert abstention_score("The corpus does not contain this measurement.")["hallucinated"] == 0.0
    invented = abstention_score("The IC50 is 25 nM.")
    assert invented["hallucinated"] == 1.0
    assert invented["abstained"] == 0.0
    assert abstention_score("I could not find any data for that pair.")["hallucinated"] == 0.0


def test_entity_retention_measures_carried_context():
    assert entity_retention("Compound 23f showed an IC50 of 40 nM", ["23f"]) == 1.0
    assert entity_retention("The compound showed an IC50 of 40 nM", ["23f"]) == 0.0


def test_context_pollution_uses_document_membership():
    assert context_pollution_by_docs(["PMC1", "PMC2", "PMC3"], {"PMC1"}) == pytest.approx(2 / 3)
    assert context_pollution_by_docs([], {"PMC1"}) == 0.0


# --- binding ----------------------------------------------------------------

def test_bind_query_set_maps_doc_keys_and_drops_unbindable():
    artifact_id = uuid4()
    query_set = QuerySet(
        name="t",
        queries=[
            EvalQuery(
                query_id="a", query_text="q", query_type="factual_single",
                gold_docs=[GoldDocRelevance(doc_key="PMC1", relevance=2)],
            ),
            EvalQuery(
                query_id="b", query_text="q", query_type="factual_single",
                gold_docs=[GoldDocRelevance(doc_key="PMC_MISSING", relevance=2)],
            ),
        ],
    )
    bound = bind_query_set(query_set, {"PMC1": artifact_id})
    assert [q.query_id for q in bound.queries] == ["a"]
    assert bound.queries[0].gold_relevance[0].artifact_id == artifact_id
    assert bound.queries[0].expected_citation_artifact_ids == [artifact_id]


def test_bind_query_set_keeps_queries_without_gold_docs():
    """Unanswerable queries have no gold documents and must survive binding."""
    query_set = QuerySet(
        name="t",
        queries=[EvalQuery(query_id="u", query_text="q", query_type="factual_single")],
    )
    assert len(bind_query_set(query_set, {}).queries) == 1


# --- generated corpus invariants -------------------------------------------

@pytest.mark.skipif(not GOLD.exists(), reason="gold corpus not built")
def test_gold_corpus_activities_join_to_paper_labels():
    corpus = load_corpus(GOLD)
    assert corpus.documents
    labelled = [a for d in corpus.documents for a in d.activities if a.label]
    assert labelled, "activities must join back to compound_record labels via record_id"
    for doc in corpus.documents:
        known = set(doc.labels)
        for act in doc.activities:
            assert act.label is None or act.label in known


@pytest.mark.skipif(not GOLD.exists(), reason="gold corpus not built")
def test_generated_queries_carry_answers_and_provenance():
    from evaluation.query_builder import QueryBuilder

    query_set = QueryBuilder(load_corpus(GOLD), seed=1).build()
    by_family: dict[str, list] = {}
    for query in query_set.queries:
        by_family.setdefault(query.family, []).append(query)

    for family in ("value_anchored", "comparative", "unanswerable", "multi_turn"):
        assert by_family.get(family), f"no {family} queries generated"

    for query in by_family["value_anchored"]:
        assert query.gold_answer and query.gold_answer.kind == "value"
        assert query.gold_answer.value is not None
        assert query.gold_docs, "a value query must name the document that reports it"
        assert query.notes.startswith("CHEMBL"), "every answer must trace to ChEMBL"

    for query in by_family["unanswerable"]:
        assert query.gold_answer.kind == "abstain"
        assert not query.gold_docs, "an unanswerable query has no relevant document"

    for query in by_family["comparative"]:
        assert query.gold_answer.choice in query.expected_entities


@pytest.mark.skipif(not GOLD.exists(), reason="gold corpus not built")
def test_multi_turn_chains_hide_the_compound_after_the_first_turn():
    """The carried entity is named in turn 0 only — that is what F6 tests."""
    from evaluation.query_builder import QueryBuilder

    query_set = QueryBuilder(load_corpus(GOLD), seed=1).build()
    chains: dict[str, list] = {}
    for query in query_set.queries:
        if query.family == "multi_turn":
            chains.setdefault(query.query_id.rsplit("-t", 1)[0], []).append(query)

    assert chains
    for turns in chains.values():
        turns.sort(key=lambda q: q.follow_up.turn_index)
        label = turns[0].expected_entities[0]
        assert label in turns[0].query_text
        assert len(label) >= 2, "single-character labels cannot be tracked across turns"
        named = re.compile(rf"(?<![\w-]){re.escape(label)}(?![\w-])")
        for follow_up in turns[1:]:
            assert not named.search(follow_up.query_text)
            assert follow_up.follow_up.prior_queries
            assert follow_up.expected_entities[0] == label


@pytest.mark.skipif(not GOLD.exists(), reason="gold corpus not built")
def test_generation_is_deterministic():
    from evaluation.query_builder import QueryBuilder

    corpus = load_corpus(GOLD)
    first = QueryBuilder(corpus, seed=42).build()
    second = QueryBuilder(corpus, seed=42).build()
    assert [q.query_text for q in first.queries] == [q.query_text for q in second.queries]
