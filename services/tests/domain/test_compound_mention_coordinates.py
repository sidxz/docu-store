"""Coordinate fields on CompoundMention (pixels of the page's _cser.png)."""

from domain.value_objects.compound_mention import CompoundMention


def test_coordinates_default_to_none_so_old_events_replay():
    # A payload exactly as written before this feature existed.
    legacy = {"smiles": "CCO", "canonical_smiles": "CCO", "is_smiles_valid": True}

    mention = CompoundMention.model_validate(legacy)

    assert mention.structure_bbox is None
    assert mention.label_bbox is None
    assert mention.structure_confidence is None
    assert mention.label_confidence is None


def test_coordinates_round_trip_through_serialization():
    mention = CompoundMention(
        smiles="CCO",
        structure_bbox=[10, 20, 110, 220],
        label_bbox=[10, 230, 60, 250],
        structure_confidence=0.91,
        label_confidence=0.77,
    )

    restored = CompoundMention.model_validate(mention.model_dump(mode="json"))

    assert restored.structure_bbox == [10, 20, 110, 220]
    assert restored.label_bbox == [10, 230, 60, 250]
    assert restored.structure_confidence == 0.91
    assert restored.label_confidence == 0.77


def test_a_pair_may_have_a_structure_but_no_label():
    # Humans can draw an unlabelled structure; the training format allows
    # "label_bbox": null.
    mention = CompoundMention(smiles="CCO", structure_bbox=[1, 2, 3, 4], label_bbox=None)

    assert mention.label_bbox is None


def test_equality_still_keys_on_canonical_smiles_not_coordinates():
    # Two mentions of the same compound in different places on the page are
    # still the same compound for dedupe purposes.
    a = CompoundMention(smiles="CCO", canonical_smiles="CCO", structure_bbox=[0, 0, 10, 10])
    b = CompoundMention(smiles="CCO", canonical_smiles="CCO", structure_bbox=[90, 90, 99, 99])

    assert a == b
    assert hash(a) == hash(b)
