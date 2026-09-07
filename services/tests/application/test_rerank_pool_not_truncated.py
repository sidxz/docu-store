"""The reranker must not cut the candidate pool for the agentic caller.

Chunk retrieval fetches ``limit * 3`` candidates so the reranker has something
to choose from. Cutting back to ``limit`` is right for the search UI, where the
number is a promise about the response length, and wrong for the chat agent,
which issues several sub-queries and merges them on best-score-per-page: a page
that ranks 11th on one sub-query and 1st on the next has to survive the first
search to be in the merge at all.
"""

from uuid import UUID, uuid4

import pytest

from application.dtos.search_dtos import HierarchicalSearchRequest
from application.ports.reranker import RerankResult
from application.ports.vector_store import PageSearchResult
from application.use_cases.search_use_cases import HierarchicalSearchUseCase

LIMIT = 10
POOL = LIMIT * 3
# Where the reranker buries the page that actually answers the question. Past
# ``limit``, so the old top_k cut deleted it. This is the measured failure: the
# embedding put it in the pool every time and the cross-encoder demoted it.
TARGET_RANK = 11


class _Reranker:
    model_name = "fake"

    def rerank(self, query, documents, top_k=None):
        """Score in candidate order, so the page at index TARGET_RANK ranks there."""
        results = [
            RerankResult(id=d.id, score=1.0 / (i + 1), original_rank=i)
            for i, d in enumerate(documents)
        ]
        return results[:top_k] if top_k else results


class _VectorStore:
    def __init__(self, results):
        self._results = results

    async def search_pages_grouped(self, **kwargs):
        return self._results[: kwargs["limit"]]


class _Empty:
    async def get_page_by_id(self, *a, **k):
        return None

    async def get_artifact_by_id(self, *a, **k):
        return None


def _use_case():
    artifact_id = uuid4()
    results = [
        PageSearchResult(
            page_id=UUID(int=i),
            artifact_id=artifact_id,
            score=1.0 - i / 100,
            page_index=i,
            metadata={"chunk_text": f"passage {i}"},
        )
        for i in range(POOL)
    ]
    return HierarchicalSearchUseCase(
        embedding_generator=None,
        vector_store=_VectorStore(results),
        summary_vector_store=None,
        page_read_model=_Empty(),
        artifact_read_model=_Empty(),
        reranker=_Reranker(),
    )


async def _search(*, keep_full_rerank_pool):
    hits, _ = await _use_case()._search_chunks(
        query_embedding=None,
        request=HierarchicalSearchRequest(query_text="q", limit=LIMIT, include_chunks=True),
        allowed_artifact_ids=None,
        workspace_id=None,
        keep_full_rerank_pool=keep_full_rerank_pool,
    )
    return hits


@pytest.mark.asyncio
async def test_search_ui_still_gets_exactly_limit():
    hits = await _search(keep_full_rerank_pool=False)
    assert len(hits) == LIMIT
    # the regression this guards: the answer page is silently gone
    assert UUID(int=TARGET_RANK) not in {h.page_id for h in hits}


@pytest.mark.asyncio
async def test_agentic_caller_keeps_the_whole_reranked_pool():
    hits = await _search(keep_full_rerank_pool=True)
    assert len(hits) == POOL
    assert UUID(int=TARGET_RANK) in {h.page_id for h in hits}


@pytest.mark.asyncio
async def test_rerank_order_is_preserved_either_way():
    """Widening the pool must not disturb the ranking, only its tail."""
    narrow = [h.page_id for h in await _search(keep_full_rerank_pool=False)]
    wide = [h.page_id for h in await _search(keep_full_rerank_pool=True)]
    assert wide[:LIMIT] == narrow


@pytest.mark.asyncio
async def test_retrieval_width_does_not_depend_on_having_a_reranker():
    """RERANKER_ENABLED=false must mean no reranking, not a third of the pool.

    Tying retrieval width to the reranker made the "no_reranking" ablation a
    two-variable change, so it measured the candidate count as much as the
    cross-encoder.
    """
    uc = _use_case()
    uc.reranker = None
    hits, info = await uc._search_chunks(
        query_embedding=None,
        request=HierarchicalSearchRequest(query_text="q", limit=LIMIT, include_chunks=True),
        allowed_artifact_ids=None,
        workspace_id=None,
        keep_full_rerank_pool=True,
    )
    assert info is None                      # nothing was reranked
    assert len(hits) == POOL                 # but the same pool was retrieved
    assert all(h.rerank_score is None for h in hits)


@pytest.mark.asyncio
async def test_limit_still_bounds_the_response_without_a_reranker():
    """The widened pool must not leak out of the search API as a bigger `limit`."""
    uc = _use_case()
    uc.reranker = None
    hits, _ = await uc._search_chunks(
        query_embedding=None,
        request=HierarchicalSearchRequest(query_text="q", limit=LIMIT, include_chunks=True),
        allowed_artifact_ids=None,
        workspace_id=None,
    )
    assert len(hits) == LIMIT
