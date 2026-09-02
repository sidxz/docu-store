"""Reranking the accumulated literature hits.

Europe PMC returns relevance order for the query the model wrote. That is not the
same as relevance to the question the user asked, and the assembly budget cuts on
whatever order it is handed.
"""

from __future__ import annotations

from uuid import uuid4

from application.ports.reranker import RerankResult
from infrastructure.chat.models import RetrievalResult
from infrastructure.chat.nodes.literature_retrieval import (
    LiteratureRetrievalNode,
    _sigmoid,
)


def _result(title: str, text: str) -> RetrievalResult:
    return RetrievalResult(
        source_type="literature",
        artifact_id=uuid4(),
        artifact_title=title,
        expanded_text=text,
        matched_text=text,
        similarity_score=1.0,
        query_source="tool_literature",
    )


class _FakeReranker:
    """Scores by a lookup on the document text, mimicking measured logits."""

    model_name = "fake"

    def __init__(self, scores: dict[str, float]) -> None:
        self._scores = scores
        self.calls: list[str] = []

    def rerank(self, query, documents, top_k=None):  # noqa: ANN001, ANN201
        self.calls.append(query)
        out = [
            RerankResult(
                id=d.id,
                score=next(v for k, v in self._scores.items() if k in d.text),
                original_rank=i,
            )
            for i, d in enumerate(documents)
        ]
        out.sort(key=lambda r: r.score, reverse=True)
        return out


def test_sigmoid_maps_measured_logits_into_the_unit_interval():
    assert _sigmoid(0.0) == 0.5
    assert 0.75 < _sigmoid(1.23) < 0.80      # real InhA inhibitor paper
    assert _sigmoid(-7.17) < 0.01            # Zi Geese INHA paper
    assert 0.0 < _sigmoid(-800.0) < 1e-6     # must not overflow


async def test_wrong_gene_papers_sort_below_relevant_ones():
    node = LiteratureRetrievalNode.__new__(LiteratureRetrievalNode)
    node._reranker = _FakeReranker({"Geese": -7.17, "inhibitor": 1.23, "preeclampsia": -4.49})

    results = [
        _result("geese", "INHA and clutch length in Zi Geese"),
        _result("preec", "INHA as a biomarker in preeclampsia"),
        _result("inha", "direct InhA inhibitor against tuberculosis"),
    ]

    ranked = await node._rescore("InhA inhibitors", results)

    assert [r.artifact_title for r in ranked] == ["inha", "preec", "geese"]
    assert ranked[0].rerank_score > 0.7
    assert ranked[-1].rerank_score < 0.01
    assert all(0.0 < r.rerank_score < 1.0 for r in ranked)


async def test_rescore_is_a_no_op_without_a_reranker():
    node = LiteratureRetrievalNode.__new__(LiteratureRetrievalNode)
    node._reranker = None

    results = [_result("a", "one"), _result("b", "two")]
    ranked = await node._rescore("q", results)

    assert ranked == results
    assert all(r.rerank_score is None for r in ranked)


async def test_the_user_question_is_what_gets_scored_not_the_models_query():
    fake = _FakeReranker({"x": 1.0})
    node = LiteratureRetrievalNode.__new__(LiteratureRetrievalNode)
    node._reranker = fake

    await node._rescore("what are known inhibitors of Pks13", [_result("a", "x")])

    assert fake.calls == ["what are known inhibitors of Pks13"]


async def test_results_beyond_the_rerank_cap_are_kept_and_sort_last():
    """The tail must survive: dropping it would silently shrink the evidence set.

    It must also never outrank a scored hit — leaving rerank_score None would
    let assembly fall back to similarity_score (a hardcoded 1.0 for literature).
    """
    from infrastructure.chat.nodes.literature_retrieval import _MAX_RERANK_CANDIDATES

    node = LiteratureRetrievalNode.__new__(LiteratureRetrievalNode)
    node._reranker = _FakeReranker({"body": -3.0})

    results = [_result(f"p{i}", "body") for i in range(_MAX_RERANK_CANDIDATES + 5)]
    ranked = await node._rescore("some question", results)

    assert len(ranked) == len(results), "no result may be discarded"
    assert all(r.rerank_score is not None for r in ranked), "None would fall back to 1.0"
    tail = ranked[-5:]
    assert all(r.rerank_score == 0.0 for r in tail)
    assert ranked[0].rerank_score > 0.0
