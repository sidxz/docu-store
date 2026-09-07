"""The chat SMILES lookup must carry the caller's workspace and ACL down.

It did not, from 9d84429 (2026-06-30) until this test existed. That commit made
the compound store fail closed on a missing workspace_id -- correctly -- but the
two chat callers were still invoking the search with the request alone. The
store raised, SearchSimilarCompoundsUseCase's blanket ``except`` turned the
raise into an ordinary Failure, and both nodes read Failure as "no matches", so
every structure a user drew resolved to nothing. Nothing was logged as an error
and no test failed. Two months.

So these assert two different things. That the scope is threaded, and that the
shape which allowed it to be dropped is gone.
"""

import inspect
from uuid import uuid4

import pytest
from returns.result import Success

from application.dtos.smiles_embedding_dtos import CompoundSearchResponse
from application.use_cases.smiles_search_use_cases import SearchSimilarCompoundsUseCase
from infrastructure.chat.nodes.query_planning import QueryPlanningNode
from infrastructure.chat.nodes.question_analysis import QuestionAnalysisNode
from infrastructure.chemistry.rdkit_smiles_validator import RdkitSmilesValidator

WS = uuid4()
ACL = [uuid4(), uuid4()]
# A real, detectable structure: the node runs the production detector, so a
# stub string would silently skip the search and pass this test for free.
QUESTION = "what do we know about CC(=O)Oc1ccccc1C(=O)O in the series?"


class _RecordingSearch:
    """Stands in for the use case, keeping the kwargs it was handed."""

    def __init__(self):
        self.calls: list[dict] = []

    async def execute(self, request, workspace_id=None, allowed_artifact_ids=None):
        self.calls.append(
            {"workspace_id": workspace_id, "allowed_artifact_ids": allowed_artifact_ids},
        )
        return Success(
            CompoundSearchResponse(
                query_smiles=request.query_smiles,
                query_canonical_smiles=request.query_smiles,
                results=[],
                total_results=0,
                model_used="test",
            ),
        )


def _validator():
    return RdkitSmilesValidator()


@pytest.mark.asyncio
async def test_question_analysis_passes_the_callers_scope_to_the_compound_search():
    search = _RecordingSearch()
    node = QuestionAnalysisNode(
        llm_client=object(),
        prompt_repository=object(),
        smiles_validator=_validator(),
        smiles_search=search,
    )

    await node._run_smiles_resolution(QUESTION, WS, ACL)

    assert search.calls, "the detector found no structure — the test proves nothing"
    assert all(c["workspace_id"] == WS for c in search.calls)
    assert all(c["allowed_artifact_ids"] == ACL for c in search.calls)


@pytest.mark.asyncio
async def test_query_planning_passes_the_callers_scope_to_the_compound_search():
    search = _RecordingSearch()
    node = QueryPlanningNode(
        llm_client=object(),
        prompt_repository=object(),
        ner_extractor=object(),
        structured_extractor=object(),
        smiles_validator=_validator(),
        smiles_search=search,
    )

    await node._run_smiles_resolution(QUESTION, WS, ACL)

    assert search.calls, "the detector found no structure — the test proves nothing"
    assert all(c["workspace_id"] == WS for c in search.calls)
    assert all(c["allowed_artifact_ids"] == ACL for c in search.calls)


def test_a_tenant_boundary_cannot_be_defaulted_away():
    """No default means an omission is a TypeError at the call site.

    That matters more than it looks: the use case wraps its body in a blanket
    ``except Exception``, so a scoping failure raised *inside* it comes back as
    an ordinary Failure. Raising at the caller instead puts it outside that try,
    where nothing swallows it.
    """
    params = inspect.signature(SearchSimilarCompoundsUseCase.execute).parameters
    assert params["workspace_id"].default is inspect.Parameter.empty
    assert params["allowed_artifact_ids"].default is inspect.Parameter.empty
    # nullable on purpose: None means "this caller has no artifact restriction"
    assert params["allowed_artifact_ids"].annotation == "list[UUID] | None"


@pytest.mark.parametrize(
    "node_cls", [QuestionAnalysisNode, QueryPlanningNode], ids=["analysis", "planning"]
)
def test_both_nodes_require_the_scope_from_their_caller(node_cls):
    """The agents hold workspace_id; a node must not be able to forget to ask."""
    params = inspect.signature(node_cls.run).parameters
    assert params["workspace_id"].default is inspect.Parameter.empty
    assert params["allowed_artifact_ids"].default is inspect.Parameter.empty
    assert params["workspace_id"].annotation == "UUID"
