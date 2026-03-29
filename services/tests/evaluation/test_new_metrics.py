"""Tests for new metric functions added for publication benchmarks."""

from evaluation.metrics import (
    detection_ap,
    entity_level_f1,
    matching_accuracy,
    ndcg_at_k_str,
    precision_at_k_str,
    recall_at_k_str,
)


class TestEntityLevelF1:
    def test_perfect_match(self):
        result = entity_level_f1({"A", "B", "C"}, {"A", "B", "C"})
        assert result["f1"] == 1.0

    def test_no_overlap(self):
        result = entity_level_f1({"A", "B"}, {"C", "D"})
        assert result["f1"] == 0.0

    def test_partial_overlap(self):
        result = entity_level_f1({"A", "B", "C"}, {"A", "D"})
        assert result["precision"] == 1 / 3
        assert result["recall"] == 1 / 2

    def test_case_insensitive(self):
        result = entity_level_f1({"Aspirin"}, {"aspirin"}, match_policy="lower")
        assert result["f1"] == 1.0

    def test_empty_predicted(self):
        result = entity_level_f1(set(), {"A", "B"})
        assert result["precision"] == 0.0
        assert result["recall"] == 0.0

    def test_empty_gold(self):
        result = entity_level_f1({"A"}, set())
        assert result["recall"] == 0.0


class TestDetectionAP:
    def test_perfect_detection(self):
        boxes = [(0, 0, 10, 10), (20, 20, 30, 30)]
        ap = detection_ap(boxes, boxes, iou_threshold=0.5)
        assert ap == 1.0

    def test_no_predictions(self):
        gold = [(0, 0, 10, 10)]
        assert detection_ap([], gold) == 0.0

    def test_no_gold(self):
        assert detection_ap([], []) == 1.0

    def test_no_overlap(self):
        pred = [(0, 0, 5, 5)]
        gold = [(100, 100, 110, 110)]
        ap = detection_ap(pred, gold, iou_threshold=0.5)
        assert ap == 0.0

    def test_partial_overlap(self):
        pred = [(100, 100, 110, 110), (0, 0, 10, 10)]  # FP first, TP second
        gold = [(0, 0, 10, 10)]
        ap = detection_ap(pred, gold, iou_threshold=0.5)
        # FP ranked before TP — AP should be less than 1
        assert 0.0 < ap < 1.0


class TestMatchingAccuracy:
    def test_perfect(self):
        pairs = [("L1", "S1"), ("L2", "S2")]
        assert matching_accuracy(pairs, pairs) == 1.0

    def test_none_correct(self):
        pred = [("L1", "S2"), ("L2", "S1")]
        gold = [("L1", "S1"), ("L2", "S2")]
        assert matching_accuracy(pred, gold) == 0.0

    def test_half_correct(self):
        pred = [("L1", "S1"), ("L2", "S1")]
        gold = [("L1", "S1"), ("L2", "S2")]
        assert matching_accuracy(pred, gold) == 0.5

    def test_empty(self):
        assert matching_accuracy([], []) == 1.0


class TestStringIDMetrics:
    def test_precision_str(self):
        retrieved = ["doc1", "doc2", "doc3"]
        relevant = {"doc1", "doc3"}
        assert precision_at_k_str(retrieved, relevant, 3) == 2 / 3

    def test_recall_str(self):
        retrieved = ["doc1", "doc2"]
        relevant = {"doc1", "doc2", "doc3"}
        assert recall_at_k_str(retrieved, relevant, 5) == 2 / 3

    def test_ndcg_str_perfect(self):
        retrieved = ["doc1", "doc2"]
        rel_map = {"doc1": 2, "doc2": 1}
        assert ndcg_at_k_str(retrieved, rel_map, 2) == 1.0

    def test_ndcg_str_reversed(self):
        retrieved = ["doc2", "doc1"]
        rel_map = {"doc1": 2, "doc2": 1}
        score = ndcg_at_k_str(retrieved, rel_map, 2)
        assert 0.0 < score < 1.0
