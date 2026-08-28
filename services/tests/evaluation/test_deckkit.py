"""The deck anchor is the one name a deck is known by.

Ingest uses it as the artifact title, the authored queries use it to scope a
question to a talk, and the hard-query generator uses it to address a deck. If
they disagree, the benchmark asks about a handle the artifact does not carry.
"""

import json

from evaluation.deck_builder import DeckCorpus
from evaluation.deckkit import MERGED_GOLD, deck_anchor


def _corpus() -> DeckCorpus:
    return DeckCorpus(**json.loads(MERGED_GOLD.read_text()))


def test_every_deck_has_an_anchor_of_usable_length():
    for deck in _corpus().decks:
        anchor = deck_anchor(deck)
        assert 15 <= len(anchor) <= 70, f"{deck.deck_id}: {anchor!r} is {len(anchor)} chars"


def test_anchors_are_unique_across_the_corpus():
    anchors = [deck_anchor(d).lower() for d in _corpus().decks]
    assert len(set(anchors)) == len(anchors), "two decks share an anchor"


def test_anchor_reads_as_a_noun_phrase():
    # It is always used as "the <anchor> deck", so it must not already say deck
    # and must not end in punctuation.
    for deck in _corpus().decks:
        anchor = deck_anchor(deck)
        assert not anchor.lower().endswith(" deck"), f"{deck.deck_id}: {anchor!r}"
        assert anchor[-1] not in ".,;:", f"{deck.deck_id}: {anchor!r}"


import pytest

from evaluation.deckkit import degloss_caption


@pytest.mark.parametrize(
    ("caption", "expected"),
    [
        # Glued paper labels — CSER reads the whole string as one label.
        ("CHEMBL4520823 · cpd 38", "CHEMBL4520823"),
        ("CHEMBL5555725 · 12", "CHEMBL5555725"),
        ("CHEMBL6144647 (8a)", "CHEMBL6144647"),
        ("CHEMBL4457622 — compound 1", "CHEMBL4457622"),
        ("CHEMBL3265214 · cpd 13d", "CHEMBL3265214"),
        ("CHEMBL4867812 · compound 6h", "CHEMBL4867812"),
        # The label may lead.
        ("39 · CHEMBL5589619", "CHEMBL5589619"),
        ("37  ·  CHEMBL5571354", "CHEMBL5571354"),
        # Must survive: trivial names.
        ("CHEMBL527 · piroxicam · the worked example",
         "CHEMBL527 · piroxicam · the worked example"),
        ("CHEMBL27 · propranolol, run in the same plate",
         "CHEMBL27 · propranolol, run in the same plate"),
        # Must survive: programme codes — this is FM2 vocabulary-gap material.
        ("K18 · CHEMBL4579042", "K18 · CHEMBL4579042"),
        ("K5  ·  CHEMBL5562987  ·  9.45 µM", "K5  ·  CHEMBL5562987  ·  9.45 µM"),
        # Mixed: strip the bare number, keep the programme code.
        ("K32 / 42 · CHEMBL5579709", "K32 · CHEMBL5579709"),
        # No registry id present — leave it entirely alone.
        ("cpd 38", "cpd 38"),
        ("compound 1 and compound 2", "compound 1 and compound 2"),
    ],
)
def test_degloss_caption(caption: str, expected: str):
    assert degloss_caption(caption) == expected
