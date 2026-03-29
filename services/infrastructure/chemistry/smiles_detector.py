"""Deterministic SMILES detection in free text.

Uses heuristic pre-filtering + RDKit validation.  No ML models, no I/O —
the only dependency is the ``SmilesValidator`` port (backed by RDKit).

References
----------
- RDKit mailing-list discussion (Dalke, Papadatos, 2016)
- Validation regex adapted from lsauer/SMILES-regex (GitHub gist)
- Papadatos heuristic: ≥ 4 carbon characters almost certainly SMILES

"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from application.ports.smiles_validator import SmilesValidator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Characters legal in SMILES notation (excludes 'J' which never appears)
_SMILES_CHARS_RE = re.compile(r"^[A-Za-z0-9@+\-\[\]\(\)\\/=%#$:.]+$")

# Structural features that distinguish SMILES from English words
_STRUCTURAL_FEATURE_RE = re.compile(r"[=\#\(\)\[\]@\\/]")

# Ring closure digits (a structural signal when combined with atom chars)
_RING_DIGIT_RE = re.compile(r"[A-Za-z]\d")

# Count carbon characters (both aromatic 'c' and aliphatic 'C')
_CARBON_RE = re.compile(r"[Cc]")

# Chemistry context keywords (case-insensitive) — relax the minimum-length
# gate when these appear near a short candidate token.
_CHEMISTRY_KEYWORDS = frozenset(
    {
        "smiles",
        "structure",
        "structures",
        "structural",
        "compound",
        "molecule",
        "molecular",
        "formula",
        "chemical",
        "chemistry",
    }
)

# Keywords that signal "find similar compounds" rather than exact lookup
_SIMILAR_KEYWORDS = frozenset(
    {
        "similar",
        "analogues",
        "analogs",
        "analogue",
        "analog",
        "related",
        "derivatives",
        "derivative",
        "scaffold",
        "sar",
        "structure-activity",
    }
)

# Tokenisation delimiters — split on whitespace + punctuation that is NOT
# part of SMILES notation.  Comma, semicolon, and question mark are safe to
# split on; parentheses and brackets are NOT (they're SMILES syntax).
_TOKEN_SPLIT_RE = re.compile(r"[\s,;?!]+")

# Minimum token length before we even consider RDKit validation
_MIN_LENGTH_DEFAULT = 5
_MIN_LENGTH_WITH_CONTEXT = 2


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DetectedSmiles:
    """A SMILES string detected in user text."""

    original: str  # as found in text (may be non-canonical)
    canonical: str  # RDKit-canonicalized form


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_smiles(
    text: str,
    validator: SmilesValidator,
    *,
    min_length: int = _MIN_LENGTH_DEFAULT,
    min_length_with_context: int = _MIN_LENGTH_WITH_CONTEXT,
) -> list[DetectedSmiles]:
    """Extract valid SMILES strings from *text*.

    Algorithm
    ---------
    1. Tokenize on whitespace / common delimiters.
    2. Pre-filter: SMILES-legal chars, has carbon, structural features or
       ≥ 4 carbon characters.
    3. Relax minimum-length gate when chemistry keywords are nearby.
    4. Validate with RDKit (``SmilesValidator.validate``).
    5. Canonicalize (``SmilesValidator.canonicalize``).

    Returns a deduplicated list of ``DetectedSmiles`` (by canonical form).
    """
    tokens = _TOKEN_SPLIT_RE.split(text.strip())
    # Clean tokens for keyword matching (strip punctuation that isn't SMILES-relevant)
    lower_tokens = {t.lower().rstrip(".!?;:,") for t in tokens}
    has_chemistry_context = bool(lower_tokens & _CHEMISTRY_KEYWORDS)

    seen_canonical: set[str] = set()
    results: list[DetectedSmiles] = []

    for token in tokens:
        # Strip trailing punctuation that may have survived tokenisation
        # (e.g. a period at the end of a sentence: "...for CCO.")
        cleaned = token.rstrip(".!?;:,")
        if not cleaned:
            continue

        # Must contain only SMILES-legal characters
        if not _SMILES_CHARS_RE.match(cleaned):
            continue

        # Must contain at least one carbon
        carbon_count = len(_CARBON_RE.findall(cleaned))
        if carbon_count == 0:
            continue

        # Must have structural features OR ≥ 4 carbons (Papadatos heuristic)
        has_structure = bool(
            _STRUCTURAL_FEATURE_RE.search(cleaned) or _RING_DIGIT_RE.search(cleaned)
        )

        # Length gate — Papadatos candidates (4+ carbons) bypass the min-length check
        if carbon_count >= 4:
            # Strong carbon signal — likely SMILES regardless of length
            pass
        elif has_chemistry_context:
            if len(cleaned) < min_length_with_context:
                continue
        elif len(cleaned) < min_length:
            continue

        # Must have structural features OR enough carbons OR explicit chemistry context
        # (chemistry keywords like "SMILES" signal the user intentionally typed a SMILES)
        if not has_structure and carbon_count < 4 and not has_chemistry_context:
            continue

        # RDKit validation — the gold standard
        if not validator.validate(cleaned):
            continue

        canonical = validator.canonicalize(cleaned)
        if canonical is None:
            continue

        # Deduplicate by canonical form
        if canonical in seen_canonical:
            continue
        seen_canonical.add(canonical)

        results.append(DetectedSmiles(original=cleaned, canonical=canonical))

    return results


def infer_smiles_search_mode(text: str) -> Literal["exact", "similar"]:
    """Determine whether the user is asking for exact or similar compound lookup.

    Scans the message for similarity-related keywords.  Default is ``"exact"``.
    """
    words = set(text.lower().split())
    if words & _SIMILAR_KEYWORDS:
        return "similar"
    return "exact"
