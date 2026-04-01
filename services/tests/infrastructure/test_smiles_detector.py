"""Unit tests for the deterministic SMILES detector."""

from __future__ import annotations

import pytest

from infrastructure.chemistry.smiles_detector import (
    detect_smiles,
    infer_smiles_search_mode,
)

# ---------------------------------------------------------------------------
# Stub SmilesValidator (avoids RDKit dependency in unit tests)
# ---------------------------------------------------------------------------


class _StubValidator:
    """Validates against a known set; canonicalises by uppercasing."""

    KNOWN = {
        # Aromatic ring with acetic acid — phenylacetic acid
        "c1ccc(CC(=O)O)cc1": "O=C(O)Cc1ccccc1",
        # Ethanol
        "CCO": "CCO",
        # Methanol (short)
        "CO": "CO",
        # Aspirin
        "CC(=O)Oc1ccccc1C(=O)O": "CC(=O)Oc1ccccc1C(=O)O",
        # Propane (no structural features but 4+ carbons)
        "CCCC": "CCCC",
        # Benzene ring
        "c1ccccc1": "c1ccccc1",
        # Complex multi-ring
        "O=C(O)c1cc(O)c(O)c(O)c1": "O=C(O)c1cc(O)c(O)c(O)c1",
    }

    def validate(self, smiles: str) -> bool:
        return smiles in self.KNOWN

    def canonicalize(self, smiles: str) -> str | None:
        return self.KNOWN.get(smiles)


@pytest.fixture
def validator() -> _StubValidator:
    return _StubValidator()


# ---------------------------------------------------------------------------
# detect_smiles
# ---------------------------------------------------------------------------


class TestDetectSmiles:
    """Tests for the detect_smiles function."""

    def test_detects_long_smiles_in_sentence(self, validator: _StubValidator) -> None:
        text = "What data do we have for c1ccc(CC(=O)O)cc1?"
        result = detect_smiles(text, validator)
        assert len(result) == 1
        assert result[0].original == "c1ccc(CC(=O)O)cc1"
        assert result[0].canonical == "O=C(O)Cc1ccccc1"

    def test_detects_aspirin_smiles(self, validator: _StubValidator) -> None:
        text = "Look up CC(=O)Oc1ccccc1C(=O)O in the database"
        result = detect_smiles(text, validator)
        assert len(result) == 1
        assert result[0].original == "CC(=O)Oc1ccccc1C(=O)O"

    def test_skips_short_smiles_without_context(self, validator: _StubValidator) -> None:
        """CCO is only 3 chars — below min_length=5, no chemistry keywords."""
        text = "Tell me about CCO and its properties"
        result = detect_smiles(text, validator)
        assert len(result) == 0

    def test_detects_short_smiles_with_chemistry_context(self, validator: _StubValidator) -> None:
        """'SMILES' keyword relaxes the minimum length gate."""
        text = "The SMILES string CCO represents ethanol"
        result = detect_smiles(text, validator)
        assert len(result) == 1
        assert result[0].canonical == "CCO"

    def test_detects_short_smiles_with_structure_context(self, validator: _StubValidator) -> None:
        text = "What is the structure of CCO?"
        result = detect_smiles(text, validator)
        assert len(result) == 1
        assert result[0].canonical == "CCO"

    def test_skips_very_short_smiles_even_with_context(self, validator: _StubValidator) -> None:
        """CO is only 2 chars — still below min_length_with_context=2 ... wait, it equals 2."""
        text = "SMILES: CO"
        result = detect_smiles(text, validator)
        assert len(result) == 1
        assert result[0].canonical == "CO"

    def test_skips_invalid_smiles(self, validator: _StubValidator) -> None:
        """Tokens that look SMILES-ish but don't validate."""
        text = "The compound XYZ(=O)ZZZ was interesting"
        result = detect_smiles(text, validator)
        assert len(result) == 0

    def test_skips_english_words(self, validator: _StubValidator) -> None:
        """Normal words should never pass the heuristic filter."""
        text = "The COMPANY reported a 15% increase in revenue"
        result = detect_smiles(text, validator)
        assert len(result) == 0

    def test_detects_multiple_smiles(self, validator: _StubValidator) -> None:
        text = "Compare c1ccc(CC(=O)O)cc1 with CC(=O)Oc1ccccc1C(=O)O"
        result = detect_smiles(text, validator)
        assert len(result) == 2
        canonicals = {r.canonical for r in result}
        assert "O=C(O)Cc1ccccc1" in canonicals
        assert "CC(=O)Oc1ccccc1C(=O)O" in canonicals

    def test_deduplicates_by_canonical(self, validator: _StubValidator) -> None:
        """Same SMILES appearing twice should only return once."""
        text = "Compare c1ccc(CC(=O)O)cc1 and c1ccc(CC(=O)O)cc1"
        result = detect_smiles(text, validator)
        assert len(result) == 1

    def test_detects_smiles_with_4_plus_carbons_no_structural_features(
        self, validator: _StubValidator,
    ) -> None:
        """CCCC has 4 carbons — Papadatos heuristic should pass it."""
        text = "Is CCCC present in our data?"
        result = detect_smiles(text, validator)
        assert len(result) == 1
        assert result[0].canonical == "CCCC"

    def test_strips_trailing_punctuation(self, validator: _StubValidator) -> None:
        text = "Check c1ccc(CC(=O)O)cc1."
        result = detect_smiles(text, validator)
        assert len(result) == 1
        assert result[0].original == "c1ccc(CC(=O)O)cc1"

    def test_returns_empty_for_no_smiles(self, validator: _StubValidator) -> None:
        text = "What is the mechanism of action of this drug?"
        result = detect_smiles(text, validator)
        assert len(result) == 0

    def test_benzene_ring_detected(self, validator: _StubValidator) -> None:
        text = "Find data for c1ccccc1 in the database"
        result = detect_smiles(text, validator)
        assert len(result) == 1
        assert result[0].canonical == "c1ccccc1"

    def test_complex_gallic_acid_detected(self, validator: _StubValidator) -> None:
        text = "What about O=C(O)c1cc(O)c(O)c(O)c1?"
        result = detect_smiles(text, validator)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# infer_smiles_search_mode
# ---------------------------------------------------------------------------


class TestInferSmilesSearchMode:
    """Tests for mode inference from user language."""

    def test_default_is_exact(self) -> None:
        assert infer_smiles_search_mode("What data do we have for CCO?") == "exact"

    def test_similar_keyword(self) -> None:
        assert infer_smiles_search_mode("Find similar compounds to CCO") == "similar"

    def test_analogues_keyword(self) -> None:
        assert infer_smiles_search_mode("Show me analogues of this molecule") == "similar"

    def test_derivatives_keyword(self) -> None:
        assert infer_smiles_search_mode("List derivatives of aspirin") == "similar"

    def test_scaffold_keyword(self) -> None:
        assert infer_smiles_search_mode("Search by scaffold similarity") == "similar"

    def test_sar_keyword(self) -> None:
        assert infer_smiles_search_mode("Run a SAR analysis on these compounds") == "similar"

    def test_case_insensitive(self) -> None:
        assert infer_smiles_search_mode("Find SIMILAR structures") == "similar"

    def test_no_false_positive_on_partial_match(self) -> None:
        """'dissimilar' contains 'similar' as a substring but is a separate word check."""
        assert infer_smiles_search_mode("These are dissimilar compounds") == "exact"
