"""Tests for evaluation.report module."""

from evaluation.report import (
    ConfigResult,
    EvalReport,
    format_latex_table,
    generate_ablation_table,
    generate_benchmark_table,
    generate_csv,
    generate_multi_turn_table,
)
from evaluation.statistics import ConfidenceInterval, SignificanceResult


class TestReportGeneration:
    def _sample_report(self) -> EvalReport:
        return EvalReport(
            config_results=[
                ConfigResult(
                    config_id=0,
                    config_name="full_system",
                    description="Full System",
                    metrics={
                        "precision_at_5": 0.8,
                        "precision_at_10": 0.7,
                        "recall_at_10": 0.9,
                        "recall_at_20": 0.95,
                        "ndcg_at_10": 0.85,
                        "context_pollution_rate": 0.1,
                        "answer_correctness": 4.2,
                        "citation_coverage": 0.88,
                        "groundedness": 0.92,
                    },
                    latency_p50_ms=1200,
                    latency_p95_ms=3500,
                ),
                ConfigResult(
                    config_id=1,
                    config_name="no_entity_filtering",
                    description="No Entity Filtering",
                    metrics={
                        "precision_at_5": 0.5,
                        "precision_at_10": 0.4,
                        "recall_at_10": 0.85,
                        "recall_at_20": 0.90,
                        "ndcg_at_10": 0.65,
                        "context_pollution_rate": 0.45,
                        "answer_correctness": 3.1,
                        "citation_coverage": 0.72,
                        "groundedness": 0.78,
                    },
                    latency_p50_ms=1400,
                    latency_p95_ms=4200,
                ),
            ],
        )

    def test_ablation_table_has_headers(self):
        report = self._sample_report()
        table = generate_ablation_table(report)
        assert "Config" in table
        assert "P@5" in table
        assert "nDCG@10" in table

    def test_ablation_table_has_rows(self):
        report = self._sample_report()
        table = generate_ablation_table(report)
        assert "full_system" in table
        assert "no_entity_filtering" in table

    def test_csv_output(self):
        report = self._sample_report()
        csv_text = generate_csv(report)
        lines = csv_text.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows
        assert "config_id" in lines[0]

    def test_multi_turn_table_empty(self):
        report = EvalReport()
        table = generate_multi_turn_table(report)
        assert "No multi-turn" in table

    def test_multi_turn_table_with_data(self):
        report = EvalReport(
            multi_turn_results=[
                {
                    "turn_index": 1,
                    "precision_with_accumulation": 0.8,
                    "precision_without_accumulation": 0.5,
                },
            ],
        )
        table = generate_multi_turn_table(report)
        assert "Delta" in table
        assert "+0.300" in table

    def test_latex_table(self):
        report = self._sample_report()
        latex = format_latex_table(report)
        assert r"\begin{table}" in latex
        assert r"\toprule" in latex
        assert r"\bottomrule" in latex
        assert "full_system" in latex.replace(r"\_", "_")
        assert "no_entity_filtering" in latex.replace(r"\_", "_")

    def test_latex_with_significance(self):
        report = self._sample_report()
        # Add significance marker to second config
        report.config_results[1].significance_vs_baseline["precision_at_5"] = SignificanceResult(
            statistic=-0.3, p_value=0.001, method="paired_bootstrap"
        )
        latex = format_latex_table(report)
        assert "**" in latex  # p < 0.01 marker

    def test_ablation_table_with_ci(self):
        report = self._sample_report()
        report.config_results[0].confidence_intervals["precision_at_5"] = ConfidenceInterval(
            mean=0.8, lower=0.75, upper=0.85
        )
        table = generate_ablation_table(report, include_ci=True)
        assert "0.750" in table
        assert "0.850" in table

    def test_benchmark_table_empty(self):
        report = EvalReport()
        table = generate_benchmark_table(report)
        assert "No public benchmark" in table

    def test_benchmark_table_with_data(self):
        from evaluation.report import BenchmarkSummary

        report = EvalReport(
            benchmark_summaries=[
                BenchmarkSummary(
                    benchmark_name="retrieval",
                    dataset_name="trec-covid",
                    metrics={"ndcg_at_10": 0.6789},
                ),
            ],
        )
        table = generate_benchmark_table(report)
        assert "retrieval" in table
        assert "trec-covid" in table
        assert "0.6789" in table
