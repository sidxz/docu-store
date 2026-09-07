"""When nothing clears the floor, the reranker must not invent a ranking.

Measured on this corpus: a passage the cross-encoder recognises scores 0.73-0.99,
while a query it cannot match collapses every candidate below 0.04 -- the ones
holding the answer included. Sorting on that noise is worse than not sorting,
because it also overwrites the first-stage similarity that did find them.
"""

import math

import pytest

from application.ports.reranker import RerankDocument
from infrastructure.rerankers.cross_encoder_reranker import (
    _DEFAULT_ABSTAIN_FLOOR,
    CrossEncoderReranker,
)

# _sigmoid inverts at logit 0 -> 0.5. The floor of 0.05 sits at logit ~-2.94.
STRONG = 2.0  # -> 0.881
NOISE = -8.0  # -> 0.000335

DOCS = [RerankDocument(id=f"d{i}", text=f"passage {i}") for i in range(5)]


class _FakeModel:
    def __init__(self, logits):
        self._logits = logits

    def predict(self, pairs):
        return self._logits[: len(pairs)]


def _reranker(logits, floor=_DEFAULT_ABSTAIN_FLOOR):
    rr = CrossEncoderReranker(abstain_floor=floor)
    rr._model = _FakeModel(logits)
    return rr


def test_abstains_when_every_candidate_is_noise():
    out = _reranker([NOISE] * 5).rerank("q", DOCS)
    assert [r.score for r in out] == [None] * 5
    # input order preserved: the caller falls back to first-stage similarity
    assert [r.id for r in out] == [d.id for d in DOCS]
    assert [r.original_rank for r in out] == [0, 1, 2, 3, 4]


def test_one_hit_does_not_certify_the_rest_of_the_pool():
    """Abstention is per candidate, not per batch.

    This is HARD-0305 in miniature. On that deck the only passage clearing the
    floor was the *title slide*, which shares words with the question and holds
    no data; the ten slides carrying the answer scored 0.0002-0.0165. A
    batch-level ``max()`` test saw 0.79, declined to abstain, and let those ten
    through as real scores -- which tiered them LOW and cut them to 200 chars.
    """
    out = _reranker([NOISE, NOISE, STRONG, NOISE, NOISE]).rerank("q", DOCS)
    assert out[0].id == "d2"
    assert out[0].score == pytest.approx(0.8808, abs=1e-4)
    # the four the model could not judge are unscored, not scored-and-terrible
    assert [r.score for r in out[1:]] == [None] * 4
    # and they keep the first-stage order behind it
    assert [r.id for r in out[1:]] == ["d0", "d1", "d3", "d4"]


def test_abstain_still_honours_top_k():
    out = _reranker([NOISE] * 5).rerank("q", DOCS, top_k=2)
    assert [r.id for r in out] == ["d0", "d1"]
    assert all(r.score is None for r in out)


def test_floor_of_zero_disables_abstention():
    out = _reranker([NOISE] * 5, floor=0.0).rerank("q", DOCS)
    assert all(r.score is not None for r in out)


def test_nan_does_not_suppress_a_real_hit():
    """A degenerate passage must not drag the pool below the floor on its own."""
    out = _reranker([math.nan, STRONG, NOISE, NOISE, NOISE]).rerank("q", DOCS)
    assert out[0].id == "d1"
    assert out[-1].id == "d0"  # nan sorts last


def test_all_nan_abstains():
    out = _reranker([math.nan] * 5).rerank("q", DOCS)
    assert all(r.score is None for r in out)
