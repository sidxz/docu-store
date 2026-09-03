"""Dedup collisions must not lose text.

The accumulator keys every view of a page under `chunk:{page_id}`, so an explicit
full-page fetch and a truncated search preview of the same page collide. Deciding
that collision on relevance alone silently deleted whatever sat past the shorter
one's cut -- for a page holding a table, the rows past the cut.
"""

from uuid import uuid4

from infrastructure.chat.models import RetrievalResult
from infrastructure.chat.retrieval_accumulator import RetrievalAccumulator

PAGE = uuid4()
ARTIFACT = uuid4()
FULL_PAGE = "| cpd | GI50 |\n| 13c | 18.3 |\n| 13h | 17.0 |\n| 13i | 8.7 |"
PREVIEW = FULL_PAGE[:30]


def _search_hit(rerank: float, text: str = PREVIEW) -> RetrievalResult:
    """What SearchDocumentsTool builds: a reranked hit carrying page text."""
    return RetrievalResult(
        source_type="chunk",
        artifact_id=ARTIFACT,
        page_id=PAGE,
        page_index=8,
        expanded_text=text,
        matched_text=text,
        similarity_score=0.62,
        rerank_score=rerank,
        query_source="tool:gi50 table",
    )


def _page_fetch(text: str = FULL_PAGE) -> RetrievalResult:
    """What GetPageContentTool builds: no rerank score, sentinel similarity."""
    return RetrievalResult(
        source_type="chunk",
        artifact_id=ARTIFACT,
        page_id=PAGE,
        page_index=8,
        expanded_text=text,
        matched_text=text[:1000],
        similarity_score=1.0,
        query_source="tool_page_content",
    )


def test_higher_scoring_short_hit_does_not_truncate_the_full_page():
    """The reported failure: a rerank score above the fetch's 1.0 sentinel."""
    acc = RetrievalAccumulator()
    acc.add_results([_page_fetch()], "fetch")
    acc.add_results([_search_hit(rerank=2.097)], "search")

    (kept,) = acc.get_all_results()
    assert kept.expanded_text == FULL_PAGE
    assert "13i" in kept.expanded_text


def test_text_survives_regardless_of_arrival_order():
    """Order-dependence is the sharp edge: retrieving more must not lose data."""
    for first, second in ((_page_fetch(), _search_hit(3.7)), (_search_hit(3.7), _page_fetch())):
        acc = RetrievalAccumulator()
        acc.add_results([first], "a")
        acc.add_results([second], "b")
        (kept,) = acc.get_all_results()
        assert kept.expanded_text == FULL_PAGE


def test_the_winner_keeps_its_own_score_pair():
    """Only text moves across.

    Stamping the loser's rerank score onto a no-rerank page fetch would demote it
    out of the HIGH tier, which tiers such a result on similarity, and re-truncate
    the very text this merge just rescued.
    """
    acc = RetrievalAccumulator()
    acc.add_results([_page_fetch()], "fetch")
    acc.add_results([_search_hit(rerank=0.46)], "search")

    (kept,) = acc.get_all_results()
    assert kept.rerank_score is None
    assert kept.similarity_score == 1.0
    assert kept.expanded_text == FULL_PAGE


def test_a_genuinely_longer_search_hit_upgrades_a_short_fetch():
    """The merge is about length, not about which tool produced it."""
    acc = RetrievalAccumulator()
    acc.add_results([_page_fetch(text="short")], "fetch")
    acc.add_results([_search_hit(rerank=0.1, text=FULL_PAGE)], "search")

    (kept,) = acc.get_all_results()
    assert kept.expanded_text == FULL_PAGE


def test_char_accounting_tracks_the_text_actually_held():
    """A wrong count here ends the retrieval loop early via is_at_capacity."""
    acc = RetrievalAccumulator()
    acc.add_results([_search_hit(rerank=2.097)], "search")
    assert acc.chars_used == len(PREVIEW)

    acc.add_results([_page_fetch()], "fetch")
    assert acc.chars_used == len(FULL_PAGE)
    assert acc.result_count == 1


def test_distinct_pages_are_not_merged():
    acc = RetrievalAccumulator()
    acc.add_results([_page_fetch()], "a")
    other = _page_fetch()
    acc.add_results([other.model_copy(update={"page_id": uuid4()})], "b")
    assert acc.result_count == 2
