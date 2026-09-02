"""Bands keep known-ceiling queries out of the headline number.

A query neither Config 0 nor Config 11 can answer contributes nothing to the
delta the paper turns on, but still counts in the denominator. Banding reports
it honestly instead of hiding it or letting it dilute.
"""

from evaluation.eval_harness import _per_query_scores
from evaluation.query_set import EvalQuery, GoldAnswer
from evaluation.report import ConfigResult


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


def _cr(per_query_results: list[dict]) -> ConfigResult:
    return ConfigResult(
        config_id=0, config_name="c", description="", per_query_results=per_query_results,
    )


def test_per_query_scores_keeps_only_headline_band():
    # A CI computed over a different population than its mean is wrong, not
    # merely incomplete: the same dilution this task removes, one level down.
    cr = _cr([
        {"query_id": "Q1", "band": "headline", "metrics": {"precision_at_5": 1.0}},
        {"query_id": "Q2", "band": "structure", "metrics": {"precision_at_5": 0.0}},
        {"query_id": "Q3", "band": "cross_deck", "metrics": {"precision_at_5": 0.0}},
        {"query_id": "Q4", "band": "headline", "metrics": {"precision_at_5": 0.5}},
    ])
    assert _per_query_scores(cr, "precision_at_5") == [1.0, 0.5]


def test_per_query_scores_treats_missing_band_as_headline():
    # An older report predating banding has no "band" key at all; it must be
    # counted, not silently dropped.
    cr = _cr([{"query_id": "Q1", "metrics": {"precision_at_5": 1.0}}])
    assert _per_query_scores(cr, "precision_at_5") == [1.0]
