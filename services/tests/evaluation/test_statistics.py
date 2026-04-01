"""Tests for evaluation.statistics module."""

from evaluation.statistics import (
    ConfidenceInterval,
    bootstrap_ci,
    cohens_d,
    paired_bootstrap_test,
    wilcoxon_signed_rank_test,
)


class TestBootstrapCI:
    def test_single_value(self):
        ci = bootstrap_ci([0.5])
        assert ci.mean == 0.5
        assert ci.lower == 0.5
        assert ci.upper == 0.5

    def test_empty(self):
        ci = bootstrap_ci([])
        assert ci.mean == 0.0

    def test_perfect_scores(self):
        ci = bootstrap_ci([1.0, 1.0, 1.0, 1.0, 1.0])
        assert ci.mean == 1.0
        assert ci.lower == 1.0
        assert ci.upper == 1.0

    def test_ci_contains_mean(self):
        values = [0.1, 0.3, 0.5, 0.7, 0.9, 0.4, 0.6, 0.8, 0.2, 0.5]
        ci = bootstrap_ci(values, seed=42)
        assert ci.lower <= ci.mean <= ci.upper

    def test_wider_ci_for_high_variance(self):
        narrow = bootstrap_ci([0.5, 0.5, 0.5, 0.5, 0.5], seed=42)
        wide = bootstrap_ci([0.0, 0.2, 0.5, 0.8, 1.0], seed=42)
        narrow_width = narrow.upper - narrow.lower
        wide_width = wide.upper - wide.lower
        assert wide_width >= narrow_width

    def test_str_format(self):
        ci = ConfidenceInterval(mean=0.800, lower=0.750, upper=0.850)
        assert "0.800" in str(ci)
        assert "0.750" in str(ci)
        assert "0.850" in str(ci)


class TestPairedBootstrapTest:
    def test_identical_scores(self):
        scores = [0.5, 0.6, 0.7, 0.8, 0.9]
        result = paired_bootstrap_test(scores, scores, seed=42)
        assert result.p_value == 1.0
        assert result.method == "paired_bootstrap"

    def test_clearly_different(self):
        baseline = [0.10, 0.12, 0.08, 0.15, 0.11, 0.09, 0.13, 0.14, 0.07, 0.10]
        system = [0.85, 0.90, 0.88, 0.92, 0.87, 0.91, 0.86, 0.89, 0.93, 0.88]
        result = paired_bootstrap_test(baseline, system, seed=42)
        assert result.p_value < 0.05
        assert result.is_significant_05

    def test_empty(self):
        result = paired_bootstrap_test([], [])
        assert result.p_value == 1.0

    def test_significance_markers(self):
        baseline = [
            0.10,
            0.12,
            0.08,
            0.15,
            0.11,
            0.09,
            0.13,
            0.14,
            0.07,
            0.10,
            0.11,
            0.08,
            0.12,
            0.09,
            0.13,
            0.10,
            0.14,
            0.07,
            0.11,
            0.12,
        ]
        system = [
            0.85,
            0.90,
            0.88,
            0.92,
            0.87,
            0.91,
            0.86,
            0.89,
            0.93,
            0.88,
            0.87,
            0.91,
            0.89,
            0.90,
            0.86,
            0.88,
            0.92,
            0.85,
            0.90,
            0.87,
        ]
        result = paired_bootstrap_test(baseline, system, seed=42)
        assert result.marker in ("*", "**")


class TestWilcoxonSignedRank:
    def test_identical_scores(self):
        scores = [0.5, 0.6, 0.7, 0.8, 0.9]
        result = wilcoxon_signed_rank_test(scores, scores)
        assert result.p_value == 1.0
        assert result.method == "wilcoxon"

    def test_clearly_different(self):
        baseline = [0.1, 0.15, 0.12, 0.11, 0.13, 0.14, 0.1, 0.12, 0.11, 0.13]
        system = [0.9, 0.85, 0.88, 0.91, 0.87, 0.89, 0.9, 0.88, 0.92, 0.86]
        result = wilcoxon_signed_rank_test(baseline, system)
        assert result.p_value < 0.05


class TestCohensD:
    def test_no_difference(self):
        scores = [0.5, 0.5, 0.5, 0.5]
        assert cohens_d(scores, scores) == 0.0

    def test_large_effect(self):
        baseline = [0.1, 0.15, 0.12, 0.11, 0.13]
        system = [0.9, 0.85, 0.88, 0.91, 0.87]
        d = cohens_d(baseline, system)
        assert d > 0.8  # large effect size

    def test_single_sample(self):
        assert cohens_d([0.5], [0.9]) == 0.0  # n < 2

    def test_empty(self):
        assert cohens_d([], []) == 0.0
