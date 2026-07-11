"""Domain service: reconcile a CSER-extracted compound label against the
document's own NER compound names, bridging only OCR glyph confusions.

CSER reads labels off page images and confuses visually-identical glyphs
(0/O, 1/I/l, 5/S, 8/B); NER reads the real name from the page text. Two labels
are treated as the same compound iff they share a *glyph skeleton* — each
confusable glyph folded to one canonical digit. The skeleton never merges two
distinct digits, so analog-series neighbours (CMX410 vs CMX411) stay distinct.

Same confusable groups as the #1 lookup fallback
(infrastructure/vector_stores/compound_qdrant_store.py). Kept independent for
now; a later cleanup may point #1 at this domain service.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

# Visually-confusable glyph groups; group[0] is the canonical fold target.
_CONFUSABLE_GROUPS = ("0Oo", "1IlL", "5S", "8B")
_FOLD = {ch: grp[0] for grp in _CONFUSABLE_GROUPS for ch in grp}


def glyph_skeleton(label: str) -> str:
    """Uppercase, strip hyphens/spaces, fold each confusable glyph to its group's
    canonical digit. Two labels are glyph-equal iff their skeletons are equal."""
    normalized = label.strip().upper().replace("-", "").replace(" ", "")
    return "".join(_FOLD.get(ch, ch) for ch in normalized)


def reconcile_label(cser_label: str, candidate_names: Iterable[str]) -> str | None:
    """Return the document name to canonicalize ``cser_label`` to, or None to keep it.

    - Match = same glyph skeleton (never bridges distinct digits).
    - If ``cser_label`` is already among the matches, keep it (return it unchanged).
    - Otherwise return the most frequent matching surface form (deterministic
      tie-break by string) — the document's preferred spelling.
    - No matches → None (keep the original; precision over recall).
    """
    if not cser_label:
        return None
    skeleton = glyph_skeleton(cser_label)
    matches = [n for n in candidate_names if n and glyph_skeleton(n) == skeleton]
    if not matches:
        return None
    if cser_label in matches:
        return cser_label
    counts = Counter(matches)
    return min(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
