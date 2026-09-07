"""The passage handed to the cross-encoder must be the chunk that matched."""

from application.use_cases.search_use_cases import _RERANK_CHARS, rerank_passage

# A slide whose table — the only part that answers the question — sits below a
# long title block. Scoring the page prefix reads the title and misses the table.
TITLE_BLOCK = "Rhodanine universe: series overview and screening cascade. " * 40
TABLE = "| Cmpd | a-syn Flu | tau Inh |\n| C-1 | 0.31 | 82% |"
PAGE = TITLE_BLOCK + TABLE


def test_prefers_stored_chunk_text():
    meta = {"chunk_text": TABLE, "chunk_index": 3, "chunk_count": 4}
    assert rerank_passage(meta, PAGE) == TABLE


def test_prepends_heading_breadcrumb():
    meta = {"chunk_text": TABLE, "section_path": ["Results", "SAR"]}
    assert rerank_passage(meta, PAGE).startswith("Results > SAR\n")


def test_window_falls_on_the_matched_chunk_not_the_prefix():
    """Without chunk_text, the window is located from chunk_index/chunk_count."""
    meta = {"chunk_index": 3, "chunk_count": 4}
    assert TABLE in rerank_passage(meta, PAGE)
    # the old behaviour — page[:2000] — would have returned title text only
    assert TABLE not in PAGE[:_RERANK_CHARS]


def test_no_chunk_position_degrades_to_prefix():
    assert rerank_passage({}, PAGE) == PAGE[:_RERANK_CHARS].strip()


def test_empty_when_nothing_to_score():
    assert rerank_passage({}, "") == ""


def test_result_is_capped():
    meta = {"chunk_text": "x" * 5000, "section_path": ["A"]}
    assert len(rerank_passage(meta, "")) == _RERANK_CHARS


def test_artifact_title_restores_what_the_embedder_indexed():
    """The reranker must see the document identity the vector carried.

    Embedding prepends build_chunk_context to every chunk before vectorising, so
    the retriever matches on document identity. Scoring the body alone left the
    reranker unable to tell one deck's assay table from another's.
    """
    meta = {"chunk_text": TABLE, "page_index": 5, "tags": ["rhodanine", "a-syn"]}
    out = rerank_passage(meta, PAGE, "Rhodanine universe")
    assert out.startswith("Document: Rhodanine universe | Tags: rhodanine, a-syn | Page 6\n\n")
    assert TABLE in out


def test_no_title_leaves_the_passage_exactly_as_it_was():
    meta = {"chunk_text": TABLE, "section_path": ["Results"]}
    assert rerank_passage(meta, PAGE, None) == rerank_passage(meta, PAGE)


def test_enriched_passage_still_respects_the_cap():
    meta = {"chunk_text": "x" * 5000, "page_index": 0}
    assert len(rerank_passage(meta, "", "A Very Long Document Title")) == _RERANK_CHARS


def test_summary_is_not_carried_into_the_rerank_passage():
    """A cross-encoder's window is small; 200 chars of prose displaces table rows."""
    meta = {"chunk_text": TABLE, "page_index": 0, "summary_candidate": "should be ignored"}
    assert "Summary:" not in rerank_passage(meta, PAGE, "Some Deck")
