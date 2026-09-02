"""Assembly for Literature mode.

The shared node tiers on thresholds tuned for the internal corpus and formats for
multi-chunk documents. Neither is true here, and the budget is small enough that
the difference decides which papers the answer is allowed to see.
"""

from __future__ import annotations

from uuid import uuid4

from infrastructure.chat.models import RetrievalResult
from infrastructure.chat.nodes.literature_context_assembly import (
    LiteratureContextAssemblyNode,
)


def _lit(title: str, score: float, chars: int = 1500) -> RetrievalResult:
    # The body must NOT repeat the title — test_a_paper_title_is_not_emitted_twice
    # counts occurrences across the whole assembled text.
    text = "Abstract body. " + ("x" * chars)
    return RetrievalResult(
        source_type="literature",
        artifact_id=uuid4(),
        artifact_title=title,
        expanded_text=text,
        matched_text=text,
        similarity_score=1.0,
        rerank_score=score,
        query_source="tool_literature",
    )


def test_the_budget_selects_by_relevance_not_by_arrival_order():
    node = LiteratureContextAssemblyNode()
    # Deliberately unsorted: assembly must not trust the order it is handed.
    results = [_lit("irrelevant", 0.01) for _ in range(20)] + [_lit("relevant", 0.95)]

    citations, text, _meta = node.run(results)

    assert "relevant" in text
    assert citations[0].artifact_title == "relevant"


def test_average_relevance_reflects_real_scores_so_verification_can_fire():
    node = LiteratureContextAssemblyNode()

    _c, _t, meta = node.run([_lit("weak", 0.02), _lit("weak2", 0.03)])

    assert meta.avg_relevance_score < 0.4, (
        "a weak result set must score below chat_verification_relevance_threshold "
        "or the LLM grounding check never runs"
    )


def test_a_paper_title_is_not_emitted_twice():
    node = LiteratureContextAssemblyNode()

    _c, text, _m = node.run([_lit("Unique Paper Title", 0.9)])

    assert text.count("Unique Paper Title") == 1


def test_abstracts_are_labelled_as_abstracts():
    node = LiteratureContextAssemblyNode()

    _c, text, _m = node.run([_lit("Some Paper", 0.9)])

    assert "ABSTRACT ONLY" in text


def test_empty_input_is_handled():
    node = LiteratureContextAssemblyNode()

    citations, text, meta = node.run([])

    assert citations == []
    assert meta.total_sources == 0
    assert "No relevant sources found." in text


def test_citation_indices_are_one_based_and_dense():
    node = LiteratureContextAssemblyNode()

    citations, _t, _m = node.run([_lit("a", 0.9), _lit("b", 0.8), _lit("c", 0.7)])

    assert [c.citation_index for c in citations] == [1, 2, 3]
    assert all(c.source_type == "literature" for c in citations)
