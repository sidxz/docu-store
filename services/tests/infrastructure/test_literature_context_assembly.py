"""Assembly for Literature mode.

The shared node tiers on thresholds tuned for the internal corpus and formats for
multi-chunk documents. Neither is true here, and the budget is small enough that
the difference decides which papers the answer is allowed to see.
"""

from __future__ import annotations

from uuid import uuid4

from infrastructure.chat.models import RetrievalResult
from infrastructure.chat.nodes.literature_context_assembly import (
    _HIGH_CHARS,
    _LOW_CHARS,
    _MEDIUM_CHARS,
    LiteratureContextAssemblyNode,
)
from infrastructure.config import settings


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


def test_a_mid_range_score_is_medium_here_not_low():
    """The sigmoid cut-points are this node's reason to exist — pin them.

    0.2 sits above this node's _MEDIUM (0.05) but below the shared node's
    _MED_RERANK (0.4). Under the inherited thresholds this abstract would be
    truncated to 200 chars and stop being usable evidence.
    """
    node = LiteratureContextAssemblyNode()

    _c, text, _m = node.run([_lit("mid", 0.2, chars=1500)])

    body = text.split("\n", 1)[1]
    assert len(body) > _LOW_CHARS + 100, "0.2 must not be treated as LOW"
    assert len(body) <= _MEDIUM_CHARS, "0.2 must be MEDIUM, not HIGH"


def test_a_result_too_big_for_the_remaining_budget_does_not_shut_out_smaller_ones():
    """A long mid-ranked abstract must not discard every shorter one below it.

    Each HIGH-tier item is capped at _HIGH_CHARS, so filling the budget takes
    several of them. The last filler is sized to leave a remainder smaller than
    one more full HIGH item but comfortably bigger than a tiny LOW-tier one —
    that remainder is where the fix (continue, not break) is provable.
    """
    node = LiteratureContextAssemblyNode()
    budget = settings.chat_context_budget_chars

    n_full = budget // _HIGH_CHARS
    full_fillers = [
        _lit(f"filler{i}", 0.99 - i * 0.001, chars=_HIGH_CHARS - 15)
        for i in range(n_full - 1)
    ]
    used_by_full = (n_full - 1) * _HIGH_CHARS
    spare = 100
    partial_display = (budget - used_by_full) - spare
    partial_filler = _lit("partial", 0.9, chars=partial_display - 15)

    results = [
        *full_fillers,
        partial_filler,
        # HIGH tier, needs a full _HIGH_CHARS — bigger than the `spare` left.
        _lit("big", 0.85, chars=_HIGH_CHARS * 2),
        # LOW tier, tiny — must still fit in what "big" could not use.
        _lit("small", 0.02, chars=10),
    ]

    citations, _t, meta = node.run(results)

    titles = [c.artifact_title for c in citations]
    assert "big" not in titles, "big must not fit in the leftover budget"
    assert "small" in titles, "a result that still fits must not be skipped"
    assert meta.total_sources >= 2
