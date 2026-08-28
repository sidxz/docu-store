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

