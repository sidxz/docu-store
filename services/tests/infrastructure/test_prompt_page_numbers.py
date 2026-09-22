"""The model is told the page number the user sees.

The UI numbers pages from 1 (CitationList, SourcesPanel: ``page_index + 1``). Every prompt
printed ``page_index`` raw, so the model read "Page 2" for the user's page 3, and any page
it named in an answer was one off.
"""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from returns.result import Success

from infrastructure.chat.models import RetrievalResult
from infrastructure.chat.nodes.context_assembly import ContextAssemblyNode
from infrastructure.chat.nodes.retrieval import RetrievalNode
from infrastructure.chat.tools.retrieval_tools import (
    SearchCompoundStructureTool,
    _format_results_for_model,
)


def _chunk(page_name=None):
    return RetrievalResult(
        source_type="chunk", artifact_id=uuid4(), page_id=uuid4(), page_index=2,
        page_name=page_name, expanded_text="text", matched_text="text",
        similarity_score=0.9, rerank_score=0.9, query_source="tool:q",
    )


def test_thinking_context_numbers_pages_from_one():
    _, text, _ = ContextAssemblyNode().run([_chunk(), _chunk("Kinase panel"), _chunk("Page 3")])
    assert "(Page 3)" in text
    assert "Kinase panel (Page 3)" in text
    assert "Page 2" not in text
    assert "Page 3 (Page 3)" not in text  # a page named by its number says it once


def test_the_retrieval_agent_numbers_pages_from_one():
    summary = _format_results_for_model([_chunk()], "q")
    assert "page 3" in summary
    assert "page 2" not in summary


def test_quick_mode_numbers_pages_from_one():
    hit = SimpleNamespace(
        page_id=uuid4(), artifact_id=uuid4(), artifact_name="Deck", page_index=2,
        page_name="Page 3", text_preview="x", rerank_score=None, score=0.8,
    )

    class Search:
        async def execute(self, request, workspace_id, allowed_artifact_ids):
            return Success(SimpleNamespace(chunk_hits=[hit], summary_hits=[]))

    class Pages:
        async def get_page_by_id(self, page_id):
            return SimpleNamespace(text_mention=SimpleNamespace(text="page text"))

    node = RetrievalNode(Search(), summary_search=None, page_read_model=Pages())
    analysis = SimpleNamespace(search_strategy="hierarchical", reformulated_query="q", entities=[])
    _, text = asyncio.run(node.run(analysis, uuid4()))
    assert "Page 3)" in text
    assert "Page 2" not in text


def test_structure_tool_numbers_pages_from_one():
    class Store:
        async def get_compounds_by_extracted_id(self, extracted_id, workspace_id, allowed_artifact_ids):
            return [SimpleNamespace(
                canonical_smiles="C", smiles="C", page_id=uuid4(), artifact_id=uuid4(),
                page_index=2, metadata=None,
            )]

    results, _, _ = asyncio.run(
        SearchCompoundStructureTool(Store()).execute({"compound_name": "X"}, uuid4(), None),
    )
    assert "page 3" in results[0].expanded_text
    assert "page 2" not in results[0].expanded_text
