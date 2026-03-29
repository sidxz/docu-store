"""Tests for evaluation.error_analysis module."""

from evaluation.error_analysis import classify_failures, summarise_failures


class TestClassifyFailures:
    def test_retrieval_miss(self):
        results = [{"query_id": "q1", "metrics": {"recall_at_20": 0.1, "precision_at_5": 0.5}}]
        failures = classify_failures(results, "test_config")
        types = {f.failure_type for f in failures}
        assert "retrieval_miss" in types

    def test_pollution(self):
        results = [{"query_id": "q1", "metrics": {"context_pollution_rate": 0.8, "recall_at_20": 0.9, "precision_at_5": 0.5}}]
        failures = classify_failures(results, "test_config")
        types = {f.failure_type for f in failures}
        assert "pollution" in types

    def test_synthesis_error(self):
        results = [{"query_id": "q1", "metrics": {"answer_correctness": 1.0, "recall_at_20": 0.9, "precision_at_5": 0.5}}]
        failures = classify_failures(results, "test_config")
        types = {f.failure_type for f in failures}
        assert "synthesis_error" in types

    def test_no_failures_for_good_metrics(self):
        results = [{
            "query_id": "q1",
            "metrics": {
                "recall_at_20": 0.9,
                "context_pollution_rate": 0.1,
                "answer_correctness": 4.5,
                "groundedness": 0.9,
                "citation_coverage": 0.9,
                "precision_at_5": 0.8,
            },
        }]
        failures = classify_failures(results, "test_config")
        assert len(failures) == 0


class TestSummariseFailures:
    def test_summary_counts(self):
        results = [
            {"query_id": "q1", "metrics": {"recall_at_20": 0.1, "precision_at_5": 0.5}},
            {"query_id": "q2", "metrics": {"context_pollution_rate": 0.9, "recall_at_20": 0.9, "precision_at_5": 0.5}},
        ]
        failures = classify_failures(results, "cfg")
        summary = summarise_failures(failures)
        assert summary["total_failures"] >= 2
        assert "by_type" in summary
        assert "worst_queries" in summary

    def test_empty_failures(self):
        summary = summarise_failures([])
        assert summary["total_failures"] == 0
