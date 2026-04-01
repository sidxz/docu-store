"""Tests for workflow trigger use cases."""

from __future__ import annotations

from uuid import uuid4

import pytest

from application.dtos.workflow_dtos import WorkflowStartedResponse
from application.workflow_use_cases.log_artifcat_sample_use_case import LogArtifactSampleUseCase
from application.workflow_use_cases.trigger_artifact_summarization_use_case import (
    TriggerArtifactSummarizationUseCase,
)
from application.workflow_use_cases.trigger_artifact_tag_aggregation_use_case import (
    TriggerArtifactTagAggregationUseCase,
)
from application.workflow_use_cases.trigger_compound_extraction_use_case import (
    TriggerCompoundExtractionUseCase,
)
from application.workflow_use_cases.trigger_doc_metadata_extraction_use_case import (
    TriggerDocMetadataExtractionUseCase,
)
from application.workflow_use_cases.trigger_embedding_use_case import TriggerEmbeddingUseCase
from application.workflow_use_cases.trigger_page_summarization_use_case import (
    TriggerPageSummarizationUseCase,
)
from application.workflow_use_cases.trigger_smiles_embedding_use_case import (
    TriggerSmilesEmbeddingUseCase,
)
from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from tests.mocks import (
    MockArtifactRepository,
    MockPageReadModel,
    MockPageRepository,
    MockWorkflowOrchestrator,
)


class TestTriggerEmbeddingUseCase:
    @pytest.mark.asyncio
    async def test_starts_workflow_and_returns_response(self) -> None:
        orchestrator = MockWorkflowOrchestrator()
        use_case = TriggerEmbeddingUseCase(orchestrator)
        page_id = uuid4()

        result = await use_case.execute(page_id=page_id, text_mention="some text")

        assert isinstance(result, WorkflowStartedResponse)
        assert result.status == "started"
        assert f"embedding-{page_id}" == result.workflow_id
        assert orchestrator.embedding_calls == [page_id]

    @pytest.mark.asyncio
    async def test_workflow_id_contains_page_id(self) -> None:
        page_id = uuid4()
        use_case = TriggerEmbeddingUseCase(MockWorkflowOrchestrator())
        result = await use_case.execute(page_id=page_id, text_mention="some text")
        assert str(page_id) in result.workflow_id

    @pytest.mark.asyncio
    async def test_skips_when_no_text_mention(self) -> None:
        use_case = TriggerEmbeddingUseCase(MockWorkflowOrchestrator())
        result = await use_case.execute(page_id=uuid4(), text_mention=None)
        assert result is None

    @pytest.mark.asyncio
    async def test_propagates_orchestrator_exception(self) -> None:
        orchestrator = MockWorkflowOrchestrator(raise_on_call=RuntimeError("Temporal down"))
        use_case = TriggerEmbeddingUseCase(orchestrator)

        with pytest.raises(RuntimeError, match="Temporal down"):
            await use_case.execute(page_id=uuid4(), text_mention="some text")


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

        assert (
            orchestrator.artifact_processing_calls[0]["storage_location"] == "/bucket/key/doc.pdf"
        )


# ============================================================================
# New trigger use case tests (for refactored use cases)
# ============================================================================


def _make_artifact_with_pages(n_pages: int = 3) -> tuple[Artifact, list[Page]]:
    """Create an artifact with N pages for trigger use case tests."""
    artifact = Artifact.create(
        source_uri=None,
        source_filename="test.pdf",
        artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF,
        storage_location="/storage/test.pdf",
    )
    pages = []
    page_ids = []
    for i in range(n_pages):
        page = Page.create(name=f"Page {i}", artifact_id=artifact.id, index=i)
        pages.append(page)
        page_ids.append(page.id)
    if page_ids:
        artifact.add_pages(page_ids)
    return artifact, pages


class TestTriggerArtifactTagAggregationUseCase:
    @pytest.mark.asyncio
    async def test_starts_workflow_with_artifact_id(self) -> None:
        orchestrator = MockWorkflowOrchestrator()
        use_case = TriggerArtifactTagAggregationUseCase(
            workflow_orchestrator=orchestrator,
        )
        artifact_id = uuid4()

        result = await use_case.execute(artifact_id=artifact_id)

        assert isinstance(result, WorkflowStartedResponse)
        assert orchestrator.artifact_tag_aggregation_calls == [artifact_id]

    @pytest.mark.asyncio
    async def test_workflow_id_contains_artifact_id(self) -> None:
        orchestrator = MockWorkflowOrchestrator()
        use_case = TriggerArtifactTagAggregationUseCase(
            workflow_orchestrator=orchestrator,
        )
        artifact_id = uuid4()

        result = await use_case.execute(artifact_id=artifact_id)

        assert str(artifact_id) in result.workflow_id

    @pytest.mark.asyncio
    async def test_propagates_orchestrator_exception(self) -> None:
        orchestrator = MockWorkflowOrchestrator(raise_on_call=RuntimeError("down"))
        use_case = TriggerArtifactTagAggregationUseCase(
            workflow_orchestrator=orchestrator,
        )

        with pytest.raises(RuntimeError, match="down"):
            await use_case.execute(artifact_id=uuid4())


class TestTriggerArtifactSummarizationUseCase:
    @pytest.mark.asyncio
    async def test_triggers_when_all_pages_summarized(self) -> None:
        artifact, _pages = _make_artifact_with_pages(3)
        artifact_repo = MockArtifactRepository()
        artifact_repo.save(artifact)
        orchestrator = MockWorkflowOrchestrator()
        # 2 summaries visible in read model + current page = 3 total
        read_model = MockPageReadModel(summary_count=2)

        use_case = TriggerArtifactSummarizationUseCase(
            artifact_repository=artifact_repo,
            page_read_model=read_model,
            workflow_orchestrator=orchestrator,
        )

        result = await use_case.execute(artifact_id=artifact.id)

        assert result is not None
        assert isinstance(result, WorkflowStartedResponse)
        assert orchestrator.artifact_summarization_calls == [artifact.id]

    @pytest.mark.asyncio
    async def test_skips_when_pages_not_ready(self) -> None:
        artifact, _pages = _make_artifact_with_pages(5)
        artifact_repo = MockArtifactRepository()
        artifact_repo.save(artifact)
        orchestrator = MockWorkflowOrchestrator()
        # Only 2 of 5 pages have summaries — not enough
        read_model = MockPageReadModel(summary_count=2)

        use_case = TriggerArtifactSummarizationUseCase(
            artifact_repository=artifact_repo,
            page_read_model=read_model,
            workflow_orchestrator=orchestrator,
        )

        result = await use_case.execute(artifact_id=artifact.id)

        assert result is None
        assert orchestrator.artifact_summarization_calls == []

    @pytest.mark.asyncio
    async def test_skips_when_no_pages(self) -> None:
        artifact, _ = _make_artifact_with_pages(0)
        artifact_repo = MockArtifactRepository()
        artifact_repo.save(artifact)
        orchestrator = MockWorkflowOrchestrator()

        use_case = TriggerArtifactSummarizationUseCase(
            artifact_repository=artifact_repo,
            page_read_model=MockPageReadModel(),
            workflow_orchestrator=orchestrator,
        )

        result = await use_case.execute(artifact_id=artifact.id)

        assert result is None

    @pytest.mark.asyncio
    async def test_propagates_orchestrator_exception(self) -> None:
        artifact, _pages = _make_artifact_with_pages(1)
        artifact_repo = MockArtifactRepository()
        artifact_repo.save(artifact)
        orchestrator = MockWorkflowOrchestrator(raise_on_call=RuntimeError("timeout"))

        use_case = TriggerArtifactSummarizationUseCase(
            artifact_repository=artifact_repo,
            page_read_model=MockPageReadModel(summary_count=1),
            workflow_orchestrator=orchestrator,
        )

        with pytest.raises(RuntimeError, match="timeout"):
            await use_case.execute(artifact_id=artifact.id)


class TestTriggerDocMetadataExtractionUseCase:
    @pytest.mark.asyncio
    async def test_starts_workflow_for_page_zero(self) -> None:
        artifact_id = uuid4()
        page = Page.create(name="Cover", artifact_id=artifact_id, index=0)
        page_repo = MockPageRepository()
        page_repo.save(page)
        orchestrator = MockWorkflowOrchestrator()

        use_case = TriggerDocMetadataExtractionUseCase(
            page_repository=page_repo,
            workflow_orchestrator=orchestrator,
        )

        result = await use_case.execute(page_id=page.id)

        assert result is not None
        assert isinstance(result, WorkflowStartedResponse)
        assert len(orchestrator.doc_metadata_calls) == 1
        assert orchestrator.doc_metadata_calls[0]["page_id"] == page.id

    @pytest.mark.asyncio
    async def test_skips_non_first_page(self) -> None:
        artifact_id = uuid4()
        page = Page.create(name="Page 2", artifact_id=artifact_id, index=1)
        page_repo = MockPageRepository()
        page_repo.save(page)
        orchestrator = MockWorkflowOrchestrator()

        use_case = TriggerDocMetadataExtractionUseCase(
            page_repository=page_repo,
            workflow_orchestrator=orchestrator,
        )

        result = await use_case.execute(page_id=page.id)

        assert result is None
        assert orchestrator.doc_metadata_calls == []

    @pytest.mark.asyncio
    async def test_uses_provided_artifact_id(self) -> None:
        page_artifact_id = uuid4()
        override_artifact_id = uuid4()
        page = Page.create(name="Cover", artifact_id=page_artifact_id, index=0)
        page_repo = MockPageRepository()
        page_repo.save(page)
        orchestrator = MockWorkflowOrchestrator()

        use_case = TriggerDocMetadataExtractionUseCase(
            page_repository=page_repo,
            workflow_orchestrator=orchestrator,
        )

        result = await use_case.execute(
            page_id=page.id,
            artifact_id=override_artifact_id,
        )

        assert result is not None
        assert orchestrator.doc_metadata_calls[0]["artifact_id"] == override_artifact_id

    @pytest.mark.asyncio
    async def test_falls_back_to_page_artifact_id(self) -> None:
        artifact_id = uuid4()
        page = Page.create(name="Cover", artifact_id=artifact_id, index=0)
        page_repo = MockPageRepository()
        page_repo.save(page)
        orchestrator = MockWorkflowOrchestrator()

        use_case = TriggerDocMetadataExtractionUseCase(
            page_repository=page_repo,
            workflow_orchestrator=orchestrator,
        )

        result = await use_case.execute(page_id=page.id)

        assert orchestrator.doc_metadata_calls[0]["artifact_id"] == artifact_id
