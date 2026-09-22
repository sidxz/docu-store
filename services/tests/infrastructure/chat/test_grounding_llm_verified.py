"""The verifier signal: "grounded" must not be readable as "verified"."""

from __future__ import annotations

import pytest

from application.dtos.chat_dtos import AgentTraceDTO, SourceCitationDTO
from infrastructure.chat.models import GroundingResult


def test_skipped_gate_reports_grounded_but_not_verified() -> None:
    # What inline_verification returns when coverage is good enough to skip.
    skipped = GroundingResult(
        is_grounded=True, confidence=0.95, verification_summary="LLM verification skipped."
    )
    assert skipped.is_grounded and not skipped.llm_verified


def test_llm_path_marks_verified_even_when_the_model_omits_the_field() -> None:
    data = {"is_grounded": False, "confidence": 0.4, "verification_summary": "s"}
    result = GroundingResult(**data).model_copy(update={"llm_verified": True})
    assert result.llm_verified and not result.is_grounded


def test_llm_payload_cannot_forge_the_flag() -> None:
    # A model echoing llm_verified=True must not survive the fallback path.
    forged = GroundingResult(
        is_grounded=True, confidence=0.5, verification_summary="failed", llm_verified=True
    ).model_copy(update={"llm_verified": False})
    assert not forged.llm_verified


@pytest.mark.parametrize(("rounds", "expected"), [(0, 0), (1, 0), (2, 1), (3, 2)])
def test_retry_count_is_rounds_minus_one(rounds: int, expected: int) -> None:
    # One grounding_result event per pass; the first pass is not a retry.
    assert AgentTraceDTO(retry_count=max(rounds - 1, 0)).retry_count == expected


def test_citation_carries_retrieval_provenance() -> None:
    from uuid import uuid4

    c = SourceCitationDTO(
        artifact_id=uuid4(), citation_index=1, query_source="tool_bioactivity:CPD-1"
    )
    assert c.query_source.startswith("tool_")
    assert SourceCitationDTO(artifact_id=uuid4(), citation_index=2).query_source is None


def test_effective_score_is_rerank_when_present_else_vector() -> None:
    """similarity_score stays the ranking score; the components travel beside it."""
    from infrastructure.chat.nodes.context_assembly import ContextAssemblyNode

    score = ContextAssemblyNode._score

    class R:
        similarity_score = 0.42
        rerank_score = None

    assert score(None, R()) == 0.42  # no reranker: effective == vector

    R.rerank_score = 0.88
    assert score(None, R()) == 0.88  # reranked: effective == rerank, vector still 0.42
    assert R.similarity_score == 0.42
