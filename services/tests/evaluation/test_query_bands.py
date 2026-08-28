"""Bands keep known-ceiling queries out of the headline number.

A query neither Config 0 nor Config 11 can answer contributes nothing to the
delta the paper turns on, but still counts in the denominator. Banding reports
it honestly instead of hiding it or letting it dilute.
"""

from evaluation.query_set import EvalQuery, GoldAnswer


def _q(**kw) -> EvalQuery:
    base = dict(
        query_id="Q1",
        query_text="t",
        query_type="factual_single",
        gold_answer=GoldAnswer(kind="value", value=1.0, unit="nM"),
    )
    return EvalQuery(**{**base, **kw})


def test_structure_queries_are_banded():
    assert _q(requires="structure").band == "structure"


def test_cross_deck_queries_are_banded():
    assert _q(capability="H4 cross-deck").band == "cross_deck"
    assert _q(capability="E2 cross-deck").band == "cross_deck"


def test_everything_else_is_headline():
    assert _q(capability="F1 identifier", requires="table").band == "headline"
    assert _q(capability="abstain", requires="absent").band == "headline"


def test_structure_wins_over_cross_deck():
    # A query that is both is a ceiling for the stronger reason: no image ever
    # reaches the model, so cross-deck scope never gets a chance to matter.
    assert _q(capability="H4 cross-deck", requires="structure").band == "structure"
