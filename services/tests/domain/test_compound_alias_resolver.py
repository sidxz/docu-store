"""Alias resolution: the CHEMBL4443524 / TAM16 split and the guards around it."""

from datetime import UTC, datetime
from uuid import uuid4

from domain.services.bioactivity_reducer import associate_bioactivities
from domain.services.compound_alias_resolver import (
    build_alias_map,
    is_publishable_alias,
    merge_compound_aliases,
)
from domain.services.tag_mention_aggregator import aggregate_tag_mentions
from domain.value_objects.tag_mention import TagMention


def _tm(tag: str, entity_type: str, params: dict | None = None, confidence: float = 0.9):
    return TagMention(
        tag=tag,
        entity_type=entity_type,
        confidence=confidence,
        date_extracted=datetime.now(UTC),
        model_name="structflo-ner",
        additional_model_params={"entity_type": entity_type} | (params or {}),
    )


def _compound(tag: str, synonyms: str | None = None, confidence: float = 0.9):
    return _tm(
        tag,
        "compound_name",
        {"synonyms": synonyms} if synonyms else None,
        confidence,
    )


def _bio(raw: str, compound: str, assay: str, value: str, unit: str = "µM"):
    return _tm(
        raw,
        "bioactivity",
        {
            "compound_name": compound,
            "assay_type": assay,
            "value": value,
            "unit": unit,
        },
    )


def test_declared_synonym_becomes_an_alias_edge():
    tags = [_compound("CHEMBL4443524", "TAM16"), _compound("TAM16")]
    assert build_alias_map(tags) == {"tam16": "chembl4443524"}


def test_activity_cited_under_the_alias_lands_on_the_canonical_compound():
    """The reported bug: the structure on CHEMBL4443524, the table on TAM16."""
    tags = [
        _compound("CHEMBL4443524", "TAM16"),
        _compound("TAM16"),
        _bio("IC50 of 0.32µM", "TAM16", "IC50", "0.32"),
        _bio("MIC of 0.08µM", "TAM16", "MIC", "0.08"),
    ]
    alias_map = build_alias_map(tags)
    merged = merge_compound_aliases(associate_bioactivities(tags, alias_map), alias_map)

    assert [tm.tag for tm in merged] == ["CHEMBL4443524"]
    params = merged[0].additional_model_params
    assert {a["assay_type"] for a in params["bioactivities"]} == {"IC50", "MIC"}
    assert params["synonyms"] == "TAM16"


def test_activity_survives_when_the_alias_has_no_compound_mention_of_its_own():
    """Previously discarded as an orphan: no TAM16 compound tag to join to."""
    tags = [
        _compound("CHEMBL4443524", "TAM16"),
        _bio("IC50 of 0.32µM", "TAM16", "IC50", "0.32"),
    ]
    result = associate_bioactivities(tags)

    assert len(result[0].additional_model_params["bioactivities"]) == 1


def test_conflicting_structures_are_never_fused():
    """A hallucinated synonym must not merge two compounds with real structures."""
    tags = [_compound("CMX410", "CMX411"), _compound("CMX411")]
    structures = {"CMX410": "CCO", "CMX411": "CCN"}

    assert build_alias_map(tags, structures) == {}
    assert build_alias_map(tags, {"CMX410": "CCO", "CMX411": "CCO"}) == {"cmx411": "cmx410"}


def test_conflicting_structures_are_not_fused_through_an_unstructured_middle():
    tags = [_compound("A", "B"), _compound("B", "C"), _compound("C")]
    alias_map = build_alias_map(tags, {"A": "CCO", "C": "CCN"})

    assert alias_map.get("c") != "a"


def test_mutual_declarations_resolve_to_one_canonical():
    """A cycle must not leave two mentions each pointing at the other."""
    alias_map = build_alias_map([_compound("Foo", "Bar"), _compound("Bar", "Foo")])

    canonicals = set(alias_map.values())
    assert len(alias_map) == 1
    assert canonicals.isdisjoint(alias_map.keys())


def test_alias_declared_on_one_page_merges_bare_mentions_on_the_others():
    page1 = [_compound("CHEMBL4443524", "TAM16")]
    page2 = [
        _compound("TAM16", confidence=0.99),
        _bio("hERG 6.9µM", "TAM16", "hERG", "6.9"),
    ]
    pages = [
        (uuid4(), 0, page1),
        (uuid4(), 1, associate_bioactivities(page2)),
    ]
    merged = aggregate_tag_mentions(pages)

    assert len(merged) == 1
    # Higher confidence on page 2, but the declared canonical still names the tag.
    assert merged[0].tag == "CHEMBL4443524"
    assert merged[0].tag_normalized == "chembl4443524"
    assert merged[0].page_count == 2
    assert "TAM16" in merged[0].additional_model_params["synonyms"]
    assert len(merged[0].additional_model_params["bioactivities"]) == 1


def test_numeric_aliases_stay_inside_the_document():
    assert build_alias_map([_compound("TAM16", "1"), _compound("1")]) == {"1": "tam16"}
    assert not is_publishable_alias("1")
    assert not is_publishable_alias(" 12 ")
    assert is_publishable_alias("1a")
    assert is_publishable_alias("TAM16")


def test_unaliased_tags_pass_through_untouched():
    tags = [_compound("Aspirin"), _tm("EGFR", "target")]
    assert merge_compound_aliases(tags, build_alias_map(tags)) == tags


def test_a_null_placeholder_is_not_an_alias():
    """The extractor writes "None" as a literal string on unaliased compounds."""
    tags = [_compound(n, "None") for n in ("Penicillin", "CMX410", "TAM16", "RIF")]

    assert build_alias_map(tags) == {}
    assert not is_publishable_alias("None")


def test_an_alias_two_compounds_both_claim_merges_nothing():
    tags = [_compound("CMX410", "hit"), _compound("CMX411", "hit"), _compound("hit")]

    assert build_alias_map(tags) == {}


def test_an_ambiguous_alias_does_not_poison_the_unambiguous_ones():
    tags = [
        _compound("CMX410", "hit, 410a"),
        _compound("CMX411", "hit"),
        _compound("410a"),
    ]

    assert build_alias_map(tags) == {"410a": "cmx410"}


def test_a_merged_card_does_not_carry_the_placeholder_forward():
    tags = [_compound("CHEMBL4443524", "TAM16, None"), _compound("TAM16")]
    alias_map = build_alias_map(tags)

    assert merge_compound_aliases(tags, alias_map)[0].additional_model_params["synonyms"] == "TAM16"
