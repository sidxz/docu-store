"""The chat SMILES lookup must carry the caller's workspace and ACL down.

The compound store fails closed on a missing workspace_id, but the two chat
callers were invoking the search with the request alone. The store raised,
SearchSimilarCompoundsUseCase's blanket ``except`` turned the raise into an
ordinary Failure, and both nodes read Failure as "no matches", so every
structure a user drew resolved to nothing. Nothing was logged and no test failed.
"""

from uuid import uuid4

import pytest
from returns.result import Success

from application.dtos.smiles_embedding_dtos import CompoundSearchResponse
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


@pytest.mark.asyncio
async def test_question_analysis_passes_the_callers_scope_to_the_compound_search():
    search = _RecordingSearch()
    node = QuestionAnalysisNode(
        llm_client=object(),
        prompt_repository=object(),
        smiles_validator=RdkitSmilesValidator(),
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
        smiles_validator=RdkitSmilesValidator(),
        smiles_search=search,
    )

    await node._run_smiles_resolution(QUESTION, WS, ACL)

    assert search.calls, "the detector found no structure — the test proves nothing"
    assert all(c["workspace_id"] == WS for c in search.calls)
    assert all(c["allowed_artifact_ids"] == ACL for c in search.calls)
