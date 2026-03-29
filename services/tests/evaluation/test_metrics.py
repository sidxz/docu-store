"""Tests for evaluation.metrics module."""

from uuid import uuid4

from evaluation.metrics import (
    aggregate_metrics,
    citation_coverage,
    context_pollution_rate,
    mean,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


class TestPrecisionAtK:
    def test_perfect_precision(self):
        ids = [uuid4() for _ in range(5)]
        relevant = set(ids)
        assert precision_at_k(ids, relevant, 5) == 1.0

    def test_zero_precision(self):
        ids = [uuid4() for _ in range(5)]
        relevant = {uuid4()}
        assert precision_at_k(ids, relevant, 5) == 0.0

    def test_partial_precision(self):
        r1, r2 = uuid4(), uuid4()
        ids = [r1, uuid4(), r2, uuid4(), uuid4()]
        relevant = {r1, r2}
        assert precision_at_k(ids, relevant, 5) == 2 / 5

    def test_k_larger_than_retrieved(self):
        r1 = uuid4()
        ids = [r1]
        relevant = {r1}
        assert precision_at_k(ids, relevant, 10) == 1.0

    def test_k_zero(self):
        assert precision_at_k([uuid4()], {uuid4()}, 0) == 0.0

    def test_empty_retrieved(self):
        assert precision_at_k([], {uuid4()}, 5) == 0.0


class TestRecallAtK:
    def test_perfect_recall(self):
        ids = [uuid4() for _ in range(3)]
        relevant = set(ids)
        assert recall_at_k(ids, relevant, 5) == 1.0

    def test_partial_recall(self):
        r1, r2, r3 = uuid4(), uuid4(), uuid4()
        ids = [r1, uuid4()]
        relevant = {r1, r2, r3}
        assert recall_at_k(ids, relevant, 5) == 1 / 3

    def test_no_relevant_docs(self):
        assert recall_at_k([uuid4()], set(), 5) == 1.0

    def test_empty_retrieved(self):
        assert recall_at_k([], {uuid4()}, 5) == 0.0


class TestNdcgAtK:
    def test_perfect_ranking(self):
        r1, r2 = uuid4(), uuid4()
        relevance_map = {r1: 2, r2: 1}
        retrieved = [r1, r2]
        score = ndcg_at_k(retrieved, relevance_map, 2)
        assert score == 1.0

    def test_reversed_ranking(self):
        r1, r2 = uuid4(), uuid4()
        relevance_map = {r1: 2, r2: 1}
        retrieved = [r2, r1]  # reversed
        score = ndcg_at_k(retrieved, relevance_map, 2)
        assert 0.0 < score < 1.0

    def test_empty(self):
        assert ndcg_at_k([], {}, 10) == 0.0

    def test_k_zero(self):
        assert ndcg_at_k([uuid4()], {uuid4(): 2}, 0) == 0.0


class TestContextPollutionRate:
    def test_no_pollution(self):
        passages = ["Compound X was tested", "Compound X showed activity"]
        rate = context_pollution_rate(passages, ["Compound X"])
        assert rate == 0.0

    def test_full_pollution(self):
        passages = ["Something about Y", "No mention of X"]
        rate = context_pollution_rate(passages, ["Compound X"])
        assert rate == 1.0

    def test_partial_pollution(self):
        passages = ["Compound X was tested", "Unrelated content"]
        rate = context_pollution_rate(passages, ["Compound X"])
        assert rate == 0.5

    def test_empty_passages(self):
        assert context_pollution_rate([], ["X"]) == 0.0

    def test_no_expected_entities(self):
        assert context_pollution_rate(["text"], []) == 0.0


class TestCitationCoverage:
    def test_all_cited(self):
        answer = "The IC50 was 2.3 uM [1]. Activity was measured at 5 nM [2]."
        cov = citation_coverage(answer)
        assert cov["ratio"] == 1.0

    def test_none_cited(self):
        answer = "The IC50 was 2.3 uM. Activity was measured at 5 nM."
        cov = citation_coverage(answer)
        assert cov["ratio"] == 0.0
        assert cov["factual_sentences"] == 2

    def test_no_factual_sentences(self):
        answer = "Hello, welcome to the system."
        cov = citation_coverage(answer)
        assert cov["factual_sentences"] == 0
        assert cov["ratio"] == 1.0  # trivially complete


class TestAggregation:
    def test_mean_empty(self):
        assert mean([]) == 0.0

    def test_mean_values(self):
        assert mean([1.0, 2.0, 3.0]) == 2.0

    def test_aggregate_metrics(self):
        per_query = [
            {"p_at_5": 1.0, "recall": 0.5},
            {"p_at_5": 0.5, "recall": 1.0},
        ]
        agg = aggregate_metrics(per_query)
        assert agg["p_at_5"] == 0.75
        assert agg["recall"] == 0.75

    def test_aggregate_empty(self):
        assert aggregate_metrics([]) == {}
