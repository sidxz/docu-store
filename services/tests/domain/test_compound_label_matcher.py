"""Pure-function tests for compound-label reconciliation (no I/O).

Mirrors the safety guarantees of the #1 lookup fallback
(tests/infrastructure/test_compound_name_matching.py): bridge glyph-identical
OCR pairs, NEVER distinct digits.
"""

from domain.services.compound_label_matcher import glyph_skeleton, reconcile_label


def test_skeleton_folds_confusable_glyphs_to_digits():
    assert glyph_skeleton("CMX41O") == glyph_skeleton("CMX410")   # letter-O == zero
    assert glyph_skeleton("GSKl23") == glyph_skeleton("GSK123")   # lowercase-L == one
    assert glyph_skeleton("GSK-286") == glyph_skeleton("gsk 286")  # hyphen/space/case


def test_skeleton_keeps_distinct_digits_distinct():
    assert glyph_skeleton("CMX410") != glyph_skeleton("CMX411")


def test_reconcile_bridges_letter_o_for_zero():
    assert reconcile_label("CMX41O", ["CMX410"]) == "CMX410"


def test_reconcile_never_bridges_distinct_digits():
    # The analog-series neighbour must never win.
    assert reconcile_label("CMX41O", ["CMX411"]) is None
    assert reconcile_label("CMX410", ["CMX411"]) is None


def test_reconcile_keeps_original_when_already_a_document_name():
    assert reconcile_label("CMX410", ["CMX410", "GSK286"]) == "CMX410"


def test_reconcile_returns_none_when_no_candidate_matches():
    assert reconcile_label("CMX41O", []) is None
    assert reconcile_label("CMX41O", ["GSK286"]) is None


def test_reconcile_picks_most_frequent_surface_form():
    # NER produced the same compound in two casings; the more frequent one wins.
    assert reconcile_label("CMX41O", ["CMX410", "cmx410", "CMX410"]) == "CMX410"
