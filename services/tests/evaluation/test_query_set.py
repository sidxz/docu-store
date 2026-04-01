"""Tests for evaluation.query_set module."""

import tempfile

from evaluation.query_set import EvalQuery, QuerySet, load_query_set, save_query_set


class TestQuerySet:
    def test_single_turn_queries(self):
        qs = QuerySet(
            name="test",
            queries=[
                EvalQuery(query_id="q1", query_text="What is X?", query_type="factual_single"),
                EvalQuery(
                    query_id="q2",
                    query_text="What about Y?",
                    query_type="follow_up",
                    follow_up={"turn_index": 1, "prior_queries": ["What is X?"]},
                ),
            ],
        )
        assert len(qs.single_turn_queries) == 1
        assert len(qs.multi_turn_queries) == 1

    def test_by_type(self):
        qs = QuerySet(
            name="test",
            queries=[
                EvalQuery(query_id="q1", query_text="A", query_type="factual_single"),
                EvalQuery(query_id="q2", query_text="B", query_type="factual_single"),
                EvalQuery(query_id="q3", query_text="C", query_type="comparative"),
            ],
        )
        by_type = qs.by_type
        assert len(by_type["factual_single"]) == 2
        assert len(by_type["comparative"]) == 1

    def test_roundtrip(self):
        qs = QuerySet(
            name="roundtrip_test",
            description="Test roundtrip",
            queries=[
                EvalQuery(
                    query_id="q1",
                    query_text="What is the IC50?",
                    query_type="factual_single",
                    expected_entities=["CompoundA", "TargetB"],
                    gold_answer_criteria=["IC50 should be 2.3 uM"],
                ),
            ],
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            save_query_set(qs, f.name)
            loaded = load_query_set(f.name)

        assert loaded.name == "roundtrip_test"
        assert len(loaded.queries) == 1
        assert loaded.queries[0].query_id == "q1"
        assert loaded.queries[0].expected_entities == ["CompoundA", "TargetB"]


class TestEvalQuery:
    def test_defaults(self):
        q = EvalQuery(query_id="q1", query_text="Test?", query_type="factual_single")
        assert q.expected_entities == []
        assert q.gold_relevance == []
        assert q.gold_answer_criteria == []
        assert q.follow_up is None
