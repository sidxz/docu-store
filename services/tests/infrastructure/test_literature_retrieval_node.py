"""Reranking the accumulated literature hits.

Europe PMC returns relevance order for the query the model wrote. That is not the
same as relevance to the question the user asked, and the assembly budget cuts on
whatever order it is handed.
"""

from __future__ import annotations

from uuid import uuid4

from application.ports.reranker import RerankResult
from infrastructure.chat.models import RetrievalResult
from infrastructure.chat.nodes import literature_retrieval
from infrastructure.chat.nodes.literature_retrieval import (
    LiteratureRetrievalNode,
    _sigmoid,
)
from infrastructure.config import settings


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


async def test_without_a_reranker_hits_are_marked_unscored_not_perfect():
    """RERANKER_ENABLED=false must not read as "every abstract is a 1.0 match".

    The tool stamps a placeholder similarity_score of 1.0, and ContextAssembly
    falls back to it when rerank_score is None -- putting every result in the
    HIGH tier and lifting avg_relevance_score above the threshold that decides
    whether the grounding check runs at all. Order is still Europe PMC's.
    """
    node = LiteratureRetrievalNode.__new__(LiteratureRetrievalNode)
    node._reranker = None

    results = [_result("a", "one"), _result("b", "two")]
    ranked = await node._rescore("q", results)

    assert [r.artifact_title for r in ranked] == [r.artifact_title for r in results]
    assert all(r.rerank_score == literature_retrieval._UNSCORED for r in ranked)
    assert literature_retrieval._UNSCORED < settings.chat_verification_relevance_threshold


async def test_run_prefers_the_plans_reformulated_query_over_the_raw_question(monkeypatch):
    """ms-marco is trained on natural-language queries. This surface also takes
    raw Europe PMC field syntax straight from the user (measured: 0.025 top
    score, 0 HIGH-tier), which the planner's natural-language reformulation
    beats regardless of what the user actually typed (measured: 0.788 top
    score, 5 HIGH-tier) -- so the reformulation must win.
    """
    from infrastructure.chat.models import QueryPlan
    from infrastructure.chat.nodes.agentic_retrieval import AgenticRetrievalNode

    async def fake_super_run(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        yield "results", [_result("a", "x")]

    monkeypatch.setattr(AgenticRetrievalNode, "run", fake_super_run)

    fake = _FakeReranker({"x": 1.0})
    node = LiteratureRetrievalNode.__new__(LiteratureRetrievalNode)
    node._reranker = fake
    plan = QueryPlan(
        query_type="factual",
        reformulated_query="known InhA inhibitors",
        search_strategy="hybrid",
        summary="",
    )

    async for _ in node.run(plan, uuid4(), None, question='TITLE_ABS:"InhA"'):
        pass

    assert fake.calls == ["known InhA inhibitors"]


async def test_run_falls_back_to_the_question_when_the_plan_has_no_reformulated_query(
    monkeypatch,
):
    from infrastructure.chat.models import QueryPlan
    from infrastructure.chat.nodes.agentic_retrieval import AgenticRetrievalNode

    async def fake_super_run(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        yield "results", [_result("a", "x")]

    monkeypatch.setattr(AgenticRetrievalNode, "run", fake_super_run)

    fake = _FakeReranker({"x": 1.0})
    node = LiteratureRetrievalNode.__new__(LiteratureRetrievalNode)
    node._reranker = fake
    plan = QueryPlan(
        query_type="factual",
        reformulated_query="",  # e.g. planning skipped, or produced nothing
        search_strategy="hybrid",
        summary="",
    )

    async for _ in node.run(plan, uuid4(), None, question="what are known inhibitors of Pks13"):
        pass

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


from infrastructure.chat.nodes.agentic_retrieval import AgenticRetrievalNode
from infrastructure.chat.retrieval_accumulator import RetrievalAccumulator
from infrastructure.config import settings


def test_default_accumulator_budget_is_unchanged_for_the_shared_node():
    """Deep Research must keep the exact behaviour it has today."""
    node = AgenticRetrievalNode(
        tool_llm=object(),
        tool_registry=object(),
        prompt_repository=object(),
    )

    assert node._accumulator_budget is None
    assert RetrievalAccumulator(node._accumulator_budget)._budget == (
        settings.chat_context_budget_chars
    )


def test_literature_gets_a_budget_large_enough_to_iterate():
    """One round of 3-4 searches accumulates 100k-173k chars (measured)."""
    node = LiteratureRetrievalNode(
        tool_llm=object(),
        tool_registry=object(),
        prompt_repository=object(),
        accumulator_budget_chars=settings.literature_accumulator_budget_chars,
    )

    # One measured round of 3-4 searches reached 173,485 chars. The budget must
    # clear that with room, or the loop still ends at iteration 0.
    assert node._accumulator_budget >= 500_000
    assert node._accumulator_budget > settings.chat_context_budget_chars * 10


class _RecordingLLM:
    """Stops the loop immediately and keeps the messages it was handed."""

    supports_native_tools = True

    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def invoke_with_tools(self, messages, tools, system_prompt=None, temperature=None):  # noqa: ANN001, ANN201, ARG002
        from application.ports.tool_calling_llm import ToolCallResult

        self.messages = messages
        return ToolCallResult(content="done")


class _StubPrompts:
    async def render_prompt(self, name, **kwargs):  # noqa: ANN001, ANN003, ANN201, ARG002
        return "system"


async def test_the_seed_does_not_call_a_tool_the_literature_registry_lacks():
    """The inherited auto-seed searches the corpus; literature has no such tool.

    Executing an unregistered name returns the string "Unknown tool:
    search_documents", which was then interpolated into the model's opening
    message as its initial search results — a dead seed and an internal error
    in the prompt, on every literature turn.
    """
    from infrastructure.chat.models import QueryPlan
    from infrastructure.chat.tools.retrieval_tools import ToolRegistry

    llm = _RecordingLLM()
    node = LiteratureRetrievalNode(
        tool_llm=llm,
        tool_registry=ToolRegistry(
            hierarchical_search=object(),
            summary_search=object(),
            page_read_model=object(),
            literature_client=object(),
            literature_only=True,
        ),
        prompt_repository=_StubPrompts(),
    )
    plan = QueryPlan(
        query_type="factual",
        reformulated_query="known InhA inhibitors",
        search_strategy="hybrid",
        summary="",
    )

    async for _ in node.run(plan, uuid4(), None, question="known InhA inhibitors"):
        pass

    assert llm.messages, "the loop must have reached the model"
    assert "Unknown tool" not in llm.messages[0]["content"]
