"""Tests for workflow trigger use cases."""

from __future__ import annotations

from uuid import uuid4

import pytest
from returns.result import Success

from application.dtos.workflow_dtos import WorkflowStartedResponse
from application.workflow_use_cases.log_artifcat_sample_use_case import LogArtifactSampleUseCase
from application.workflow_use_cases.trigger_compound_extraction_use_case import (
    TriggerCompoundExtractionUseCase,
)
from application.workflow_use_cases.trigger_embedding_use_case import TriggerEmbeddingUseCase
from application.workflow_use_cases.trigger_page_summarization_use_case import (
    TriggerPageSummarizationUseCase,
)
from application.workflow_use_cases.trigger_smiles_embedding_use_case import (
    TriggerSmilesEmbeddingUseCase,
)
from tests.mocks import MockWorkflowOrchestrator


class TestTriggerEmbeddingUseCase:

    @pytest.mark.asyncio
    async def test_starts_workflow_and_returns_response(self) -> None:
        orchestrator = MockWorkflowOrchestrator()
        use_case = TriggerEmbeddingUseCase(orchestrator)
        page_id = uuid4()

        result = await use_case.execute(page_id=page_id)

        assert isinstance(result, WorkflowStartedResponse)
        assert result.status == "started"
        assert f"embedding-{page_id}" == result.workflow_id
        assert orchestrator.embedding_calls == [page_id]

    @pytest.mark.asyncio
    async def test_workflow_id_contains_page_id(self) -> None:
        page_id = uuid4()
        use_case = TriggerEmbeddingUseCase(MockWorkflowOrchestrator())
        result = await use_case.execute(page_id=page_id)
        assert str(page_id) in result.workflow_id

    @pytest.mark.asyncio
    async def test_propagates_orchestrator_exception(self) -> None:
        orchestrator = MockWorkflowOrchestrator(raise_on_call=RuntimeError("Temporal down"))
        use_case = TriggerEmbeddingUseCase(orchestrator)

        with pytest.raises(RuntimeError, match="Temporal down"):
            await use_case.execute(page_id=uuid4())


class TestTriggerCompoundExtractionUseCase:

    @pytest.mark.asyncio
    async def test_starts_workflow_and_returns_response(self) -> None:
        orchestrator = MockWorkflowOrchestrator()
        use_case = TriggerCompoundExtractionUseCase(orchestrator)
        page_id = uuid4()

        result = await use_case.execute(page_id=page_id)

        assert isinstance(result, WorkflowStartedResponse)
        assert result.status == "started"
        assert f"compound-extraction-{page_id}" == result.workflow_id
        assert orchestrator.compound_extraction_calls == [page_id]

    @pytest.mark.asyncio
    async def test_propagates_orchestrator_exception(self) -> None:
        orchestrator = MockWorkflowOrchestrator(raise_on_call=RuntimeError("connection refused"))
        use_case = TriggerCompoundExtractionUseCase(orchestrator)

        with pytest.raises(RuntimeError):
            await use_case.execute(page_id=uuid4())


class TestTriggerSmilesEmbeddingUseCase:

    @pytest.mark.asyncio
    async def test_starts_workflow_and_returns_response(self) -> None:
        orchestrator = MockWorkflowOrchestrator()
        use_case = TriggerSmilesEmbeddingUseCase(orchestrator)
        page_id = uuid4()

        result = await use_case.execute(page_id=page_id)

        assert isinstance(result, WorkflowStartedResponse)
        assert result.status == "started"
        assert f"smiles-embedding-{page_id}" == result.workflow_id
        assert orchestrator.smiles_embedding_calls == [page_id]

    @pytest.mark.asyncio
    async def test_propagates_orchestrator_exception(self) -> None:
        orchestrator = MockWorkflowOrchestrator(raise_on_call=RuntimeError("timeout"))
        use_case = TriggerSmilesEmbeddingUseCase(orchestrator)

        with pytest.raises(RuntimeError):
            await use_case.execute(page_id=uuid4())


class TestTriggerPageSummarizationUseCase:

    @pytest.mark.asyncio
    async def test_starts_workflow_and_returns_response(self) -> None:
        orchestrator = MockWorkflowOrchestrator()
        use_case = TriggerPageSummarizationUseCase(orchestrator)
        page_id = uuid4()

        result = await use_case.execute(page_id=page_id)

        assert isinstance(result, WorkflowStartedResponse)
        assert result.status == "started"
        assert f"page-summarization-{page_id}" == result.workflow_id
        assert orchestrator.page_summarization_calls == [page_id]

    @pytest.mark.asyncio
    async def test_propagates_orchestrator_exception(self) -> None:
        orchestrator = MockWorkflowOrchestrator(raise_on_call=RuntimeError("timeout"))
        use_case = TriggerPageSummarizationUseCase(orchestrator)

        with pytest.raises(RuntimeError):
            await use_case.execute(page_id=uuid4())


class TestLogArtifactSampleUseCase:

    @pytest.mark.asyncio
    async def test_starts_workflow_and_returns_response(self) -> None:
        orchestrator = MockWorkflowOrchestrator()
        use_case = LogArtifactSampleUseCase(orchestrator)
        artifact_id = uuid4()
        storage = "/storage/artifact.pdf"

        result = await use_case.execute(artifact_id=artifact_id, storage_location=storage)

        assert isinstance(result, WorkflowStartedResponse)
        assert result.status == "started"
        assert result.workflow_id == str(artifact_id)
        assert len(orchestrator.artifact_processing_calls) == 1
        call = orchestrator.artifact_processing_calls[0]
        assert call["artifact_id"] == artifact_id
        assert call["storage_location"] == storage

    @pytest.mark.asyncio
    async def test_workflow_id_is_artifact_id_string(self) -> None:
        artifact_id = uuid4()
        use_case = LogArtifactSampleUseCase(MockWorkflowOrchestrator())
        result = await use_case.execute(artifact_id=artifact_id, storage_location="/s/f.pdf")
        assert result.workflow_id == str(artifact_id)

    @pytest.mark.asyncio
    async def test_propagates_orchestrator_exception(self) -> None:
        orchestrator = MockWorkflowOrchestrator(raise_on_call=RuntimeError("Temporal unavailable"))
        use_case = LogArtifactSampleUseCase(orchestrator)

        with pytest.raises(RuntimeError, match="Temporal unavailable"):
            await use_case.execute(artifact_id=uuid4(), storage_location="/s/f.pdf")

    @pytest.mark.asyncio
    async def test_passes_storage_location_to_orchestrator(self) -> None:
        orchestrator = MockWorkflowOrchestrator()
        use_case = LogArtifactSampleUseCase(orchestrator)
        artifact_id = uuid4()

        await use_case.execute(artifact_id=artifact_id, storage_location="/bucket/key/doc.pdf")

        assert orchestrator.artifact_processing_calls[0]["storage_location"] == "/bucket/key/doc.pdf"
