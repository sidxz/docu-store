"""Alias resolution: the CHEMBL4443524 / TAM16 split and the guards around it."""

from datetime import UTC, datetime
from uuid import uuid4

from domain.services.bioactivity_reducer import associate_bioactivities
from domain.services.compound_alias_resolver import (
    build_alias_map,
    is_publishable_alias,
    merge_compound_aliases,
    normalize,
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


def _bio(
    raw: str,
    compound: str,
    endpoint: str,
    value: str,
    unit: str = "µM",
    assay: str | None = None,
    strain: str | None = None,
):
    return _tm(
        raw,
        "bioactivity",
        {
            "compound_name": compound,
            "assay_type": endpoint,
            "value": value,
            "unit": unit,
        }
        | ({"assay": assay} if assay else {})
        | ({"strain": strain} if strain else {}),
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


def test_a_deck_label_yields_to_any_other_name():
    """NER declares the registry ID or partner code as the synonym of the table's label."""
    for label, name in [
        ("8d", "CHEMBL6133834"),
        ("7a", "SACC-3060"),
        ("12", "ChemBridge 5102345"),
        ("Compound 9b", "Bedaquiline"),
    ]:
        tags = [_compound(label, name), _compound(name)]

        assert build_alias_map(tags) == {normalize(label): normalize(name)}


def test_between_two_real_names_ners_primary_still_wins():
    tags = [_compound("Bedaquiline", "CHEMBL376140"), _compound("CHEMBL376140")]

    assert build_alias_map(tags) == {"chembl376140": "bedaquiline"}


def test_card_takes_the_canonical_name_even_without_a_mention_of_its_own():
    """The registry ID only ever appeared as '8d's synonym; the card and its row still land."""
    tags = [_compound("8d", "CHEMBL6133834"), _bio("CC50 of 15.3 µM", "8d", "CC50", "15.3")]
    alias_map = build_alias_map(tags)
    merged = merge_compound_aliases(associate_bioactivities(tags, alias_map), alias_map)

    assert merged[0].tag == "CHEMBL6133834"
    assert merged[0].additional_model_params["synonyms"] == "8d"
    assert len(merged[0].additional_model_params["bioactivities"]) == 1


def test_a_value_repeated_across_assays_is_not_collapsed():
    """8t reads >20.0 in three of four cytotoxicity assays, and NER types all four CC50."""
    tags = [
        _compound("8t", "CHEMBL6153006"),
        _compound("CHEMBL6153006"),
        *[_bio("CC50 of >20.0 µM", "8t", "CC50", ">20.0") for _ in range(3)],
        _bio("CC50 of 11.8 µM", "8t", "CC50", "11.8"),
    ]
    alias_map = build_alias_map(tags)
    merged = merge_compound_aliases(associate_bioactivities(tags, alias_map), alias_map)

    assert len(merged[0].additional_model_params["bioactivities"]) == 4


def test_the_assay_rides_along_and_tells_equal_values_apart():
    """8t reads >20.0 on two slides, in different assays: two measurements, not one."""

    def page(assay: str) -> list[TagMention]:
        return [_compound("8t"), _bio(">20.0", "8t", "CC50", ">20.0", assay=assay)]

    pages = [
        (uuid4(), 0, associate_bioactivities(page("HepG2 MTT"))),
        (uuid4(), 1, associate_bioactivities(page("Vero NR"))),
    ]
    activities = aggregate_tag_mentions(pages)[0].additional_model_params["bioactivities"]

    assert [a["assay"] for a in activities] == ["HepG2 MTT", "Vero NR"]
    unstated = associate_bioactivities(page("None"))[0].additional_model_params
    assert "assay" not in unstated["bioactivities"][0]


def test_the_strain_rides_along_and_tells_equal_values_apart():
    """CHEMBL126 reads MIC 16 µg/mL against two S. aureus strains: two measurements, and
    the strain is what says which is which. NER writes it; the reducer used to drop it."""

    def page(strain: str) -> list[TagMention]:
        return [_compound("CHEMBL126"), _bio("16", "CHEMBL126", "MIC", "16", "µg/mL", strain=strain)]

    pages = [
        (uuid4(), 0, associate_bioactivities(page("ATCC 29213"))),
        (uuid4(), 1, associate_bioactivities(page("ATCC 27660"))),
    ]
    activities = aggregate_tag_mentions(pages)[0].additional_model_params["bioactivities"]

    assert [a["strain"] for a in activities] == ["ATCC 29213", "ATCC 27660"]
    unstated = associate_bioactivities(page("None"))[0].additional_model_params
    assert "strain" not in unstated["bioactivities"][0]


def test_a_merged_card_does_not_carry_the_placeholder_forward():
    tags = [_compound("CHEMBL4443524", "TAM16, None"), _compound("TAM16")]
    alias_map = build_alias_map(tags)

    assert merge_compound_aliases(tags, alias_map)[0].additional_model_params["synonyms"] == "TAM16"


def test_a_value_survives_without_an_endpoint_when_its_assay_names_one():
    """A column headed "FP (µM)" states the assay and no endpoint, so NER writes
    assay_type "None": the measurement is still real. A value with neither is not."""
    tags = [
        _compound("CHEMBL4464825", "27"),
        _bio("2", "CHEMBL4464825", "None", "2", assay="FP"),
        _bio("1.5", "CHEMBL4464825", "None", "1.5", assay="PPIase"),
        _bio("9.9", "CHEMBL4464825", "None", "9.9"),
    ]
    rows = associate_bioactivities(tags, build_alias_map(tags))[0].additional_model_params[
        "bioactivities"
    ]

    assert [(r.get("assay_type", ""), r["value"], r.get("assay")) for r in rows] == [
        ("", "2", "FP"),
        ("", "1.5", "PPIase"),
    ]
