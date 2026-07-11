"""Pure-function tests for compound-id matching (no Qdrant needed).

Covers the glyph-confusion fallback that resolves CSER OCR mismatches like
"CMX410" (query, digit-zero) vs "CMX41O" (stored, letter-O).
"""

from infrastructure.vector_stores.compound_qdrant_store import (
    _MAX_CONFUSABLE_POS,
    _compound_name_variants,
    _confusable_variants,
)


def test_bridges_letter_o_for_zero_both_directions():
    # The real bug: user/NER "CMX410" must reach stored "CMX41O".
    assert "CMX41O" in _confusable_variants("CMX410")
    assert "CMX410" in _confusable_variants("CMX41O")


def test_bridges_one_and_letter_i_or_l():
    assert "GSKI23" in _confusable_variants("GSK123")  # 1 -> I
    assert "GSK123" in _confusable_variants("GSKl23")  # l -> 1


def test_does_not_bridge_distinct_digits():
    # Analog-series neighbours are DIFFERENT compounds — must never collide.
    assert "CMX411" not in _confusable_variants("CMX410")
    assert "CMX410" not in _confusable_variants("CMX411")


def test_bounded_on_long_ambiguous_ids():
    # More than _MAX_CONFUSABLE_POS swappable glyphs per base form -> skipped,
    # so the MatchAny filter can never explode.
    ident = "O" * (_MAX_CONFUSABLE_POS + 1)
    assert _confusable_variants(ident) == []


def test_formatting_variants_still_work():
    v = _compound_name_variants("GSK286")
    assert "GSK-286" in v
    assert "GSK 286" in v
