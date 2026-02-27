"""Tests for page summarization use cases."""

from __future__ import annotations

from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.use_cases.summarization_use_cases import SummarizePageUseCase
from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.text_mention import TextMention
from tests.mocks import (
    MockArtifactRepository,
    MockBlobStore,
    MockExternalEventPublisher,
    MockLLMClient,
    MockPageRepository,
    MockPromptRepository,
)

# The threshold in the use case (100 chars)
_SHORT_TEXT = "Short."
_LONG_TEXT = "A" * 101


def _make_artifact() -> Artifact:
    return Artifact.create(
        source_uri=None,
        source_filename="slides.pdf",
        artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF,
        storage_location="/storage/slides.pdf",
    )


def _make_page(artifact_id, text: str | None = None) -> Page:
    page = Page.create(name="Slide 1", artifact_id=artifact_id, index=0)
    if text:
        page.update_text_mention(TextMention(text=text))
    return page


def _setup(
    text: str | None = _LONG_TEXT,
    image_exists: bool = True,
    llm_response: str = "Generated summary.",
    publisher=None,
):
    artifact = _make_artifact()
    page = _make_page(artifact.id, text)

    artifact_repo = MockArtifactRepository()
    artifact_repo.artifacts[artifact.id] = artifact
    page_repo = MockPageRepository()
    page_repo.pages[page.id] = page

    use_case = SummarizePageUseCase(
        page_repository=page_repo,
        artifact_repository=artifact_repo,
        llm_client=MockLLMClient(response=llm_response),
        prompt_repository=MockPromptRepository(),
        blob_store=MockBlobStore(exists_result=image_exists, bytes_result=b"png-bytes"),
        external_event_publisher=publisher,
    )
    return use_case, page, page_repo


class TestSummarizePageUseCase:

    @pytest.mark.asyncio
    async def test_hybrid_mode_when_long_text_and_image(self) -> None:
        use_case, page, page_repo = _setup(text=_LONG_TEXT, image_exists=True)

        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        response = result.unwrap()
        saved = page_repo.pages[page.id]
        assert saved.summary_candidate is not None
        assert saved.summary_candidate.additional_model_params["mode"] == "hybrid"

    @pytest.mark.asyncio
    async def test_hybrid_mode_uses_complete_with_image(self) -> None:
        llm = MockLLMClient(response="Hybrid summary")
        artifact = _make_artifact()
        page = _make_page(artifact.id, _LONG_TEXT)

        artifact_repo = MockArtifactRepository()
        artifact_repo.artifacts[artifact.id] = artifact
        page_repo = MockPageRepository()
        page_repo.pages[page.id] = page

        use_case = SummarizePageUseCase(
            page_repository=page_repo,
            artifact_repository=artifact_repo,
            llm_client=llm,
            prompt_repository=MockPromptRepository(),
            blob_store=MockBlobStore(exists_result=True),
        )
        await use_case.execute(page.id)

        assert len(llm.complete_with_image_calls) == 1

    @pytest.mark.asyncio
    async def test_hybrid_falls_back_to_text_only_when_no_image(self) -> None:
        llm = MockLLMClient()
        artifact = _make_artifact()
        page = _make_page(artifact.id, _LONG_TEXT)

        artifact_repo = MockArtifactRepository()
        artifact_repo.artifacts[artifact.id] = artifact
        page_repo = MockPageRepository()
        page_repo.pages[page.id] = page

        use_case = SummarizePageUseCase(
            page_repository=page_repo,
            artifact_repository=artifact_repo,
            llm_client=llm,
            prompt_repository=MockPromptRepository(),
            blob_store=MockBlobStore(exists_result=False),
        )
        await use_case.execute(page.id)

        # Image doesn't exist → falls back to text complete()
        assert len(llm.complete_calls) == 1
        assert len(llm.complete_with_image_calls) == 0

    @pytest.mark.asyncio
    async def test_image_only_mode_when_short_text_and_image_exists(self) -> None:
        use_case, page, page_repo = _setup(text=_SHORT_TEXT, image_exists=True)

        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        saved = page_repo.pages[page.id]
        assert saved.summary_candidate.additional_model_params["mode"] == "image_only"

    @pytest.mark.asyncio
    async def test_text_only_mode_when_no_image_and_short_text(self) -> None:
        use_case, page, page_repo = _setup(text=_SHORT_TEXT, image_exists=False)

        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        saved = page_repo.pages[page.id]
        assert saved.summary_candidate.additional_model_params["mode"] == "text_only"

    @pytest.mark.asyncio
    async def test_text_only_mode_when_no_text_mention(self) -> None:
        use_case, page, page_repo = _setup(text=None, image_exists=False)

        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        saved = page_repo.pages[page.id]
        assert saved.summary_candidate.additional_model_params["mode"] == "text_only"

    @pytest.mark.asyncio
    async def test_skips_locked_summary(self) -> None:
        artifact = _make_artifact()
        page = _make_page(artifact.id, _LONG_TEXT)
        locked = SummaryCandidate(summary="Human correction", confidence=1.0, is_locked=True)
        page.update_summary_candidate(locked)

        artifact_repo = MockArtifactRepository()
        artifact_repo.artifacts[artifact.id] = artifact
        page_repo = MockPageRepository()
        page_repo.pages[page.id] = page
        llm = MockLLMClient()

        use_case = SummarizePageUseCase(
            page_repository=page_repo,
            artifact_repository=artifact_repo,
            llm_client=llm,
            prompt_repository=MockPromptRepository(),
            blob_store=MockBlobStore(),
        )
        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        # LLM was never called
        assert len(llm.complete_calls) == 0
        assert len(llm.complete_with_image_calls) == 0
        # Summary unchanged
        assert page_repo.pages[page.id].summary_candidate.summary == "Human correction"

    @pytest.mark.asyncio
    async def test_summary_saved_and_not_locked(self) -> None:
        use_case, page, page_repo = _setup(llm_response="New summary text.")

        result = await use_case.execute(page.id)

        assert isinstance(result, Success)
        saved = page_repo.pages[page.id]
        assert saved.summary_candidate.summary == "New summary text."
        assert saved.summary_candidate.is_locked is False
        assert page_repo.save_called

    @pytest.mark.asyncio
    async def test_model_name_constructed_from_llm_info(self) -> None:
        use_case, page, page_repo = _setup()
        await use_case.execute(page.id)

        # MockLLMClient returns {"provider": "mock", "model_name": "mock-model"}
        saved = page_repo.pages[page.id]
        assert saved.summary_candidate.model_name == "mock/mock-model"

    @pytest.mark.asyncio
    async def test_notifies_publisher_on_success(self) -> None:
        publisher = MockExternalEventPublisher()
        use_case, page, _ = _setup(publisher=publisher)

        await use_case.execute(page.id)

        assert publisher.page_updated_called

    @pytest.mark.asyncio
    async def test_prompt_rendered_with_correct_name_hybrid(self) -> None:
        prompt_repo = MockPromptRepository()
        artifact = _make_artifact()
        page = _make_page(artifact.id, _LONG_TEXT)

        artifact_repo = MockArtifactRepository()
        artifact_repo.artifacts[artifact.id] = artifact
        page_repo = MockPageRepository()
        page_repo.pages[page.id] = page

        use_case = SummarizePageUseCase(
            page_repository=page_repo,
            artifact_repository=artifact_repo,
            llm_client=MockLLMClient(),
            prompt_repository=prompt_repo,
            blob_store=MockBlobStore(exists_result=True),
        )
        await use_case.execute(page.id)

        assert prompt_repo.render_calls[0]["name"] == "page_summarization_hybrid"

    @pytest.mark.asyncio
    async def test_prompt_rendered_with_correct_name_image_only(self) -> None:
        prompt_repo = MockPromptRepository()
        artifact = _make_artifact()
        page = _make_page(artifact.id, _SHORT_TEXT)

        artifact_repo = MockArtifactRepository()
        artifact_repo.artifacts[artifact.id] = artifact
        page_repo = MockPageRepository()
        page_repo.pages[page.id] = page

        use_case = SummarizePageUseCase(
            page_repository=page_repo,
            artifact_repository=artifact_repo,
            llm_client=MockLLMClient(),
            prompt_repository=prompt_repo,
            blob_store=MockBlobStore(exists_result=True),
        )
        await use_case.execute(page.id)

        assert prompt_repo.render_calls[0]["name"] == "page_summarization_image_only"

    @pytest.mark.asyncio
    async def test_fails_when_page_not_found(self) -> None:
        artifact = _make_artifact()
        artifact_repo = MockArtifactRepository()
        artifact_repo.artifacts[artifact.id] = artifact

        use_case = SummarizePageUseCase(
            page_repository=MockPageRepository(),
            artifact_repository=artifact_repo,
            llm_client=MockLLMClient(),
            prompt_repository=MockPromptRepository(),
            blob_store=MockBlobStore(),
        )
        result = await use_case.execute(uuid4())

        assert isinstance(result, Failure)
        assert result.failure().category == "not_found"

    @pytest.mark.asyncio
    async def test_fails_when_artifact_not_found(self) -> None:
        page = _make_page(uuid4(), _LONG_TEXT)
        page_repo = MockPageRepository()
        page_repo.pages[page.id] = page

        use_case = SummarizePageUseCase(
            page_repository=page_repo,
            artifact_repository=MockArtifactRepository(),
            llm_client=MockLLMClient(),
            prompt_repository=MockPromptRepository(),
            blob_store=MockBlobStore(),
        )
        result = await use_case.execute(page.id)

        assert isinstance(result, Failure)
        assert result.failure().category == "not_found"

    @pytest.mark.asyncio
    async def test_fails_when_llm_raises(self) -> None:
        use_case, page, _ = _setup(
            llm_response="unused",
        )
        # Re-build with raising LLM
        artifact = _make_artifact()
        page2 = _make_page(artifact.id, _LONG_TEXT)
        artifact_repo = MockArtifactRepository()
        artifact_repo.artifacts[artifact.id] = artifact
        page_repo = MockPageRepository()
        page_repo.pages[page2.id] = page2

        use_case2 = SummarizePageUseCase(
            page_repository=page_repo,
            artifact_repository=artifact_repo,
            llm_client=MockLLMClient(raise_on_call=RuntimeError("LLM timeout")),
            prompt_repository=MockPromptRepository(),
            blob_store=MockBlobStore(),
        )
        result = await use_case2.execute(page2.id)

        assert isinstance(result, Failure)
        assert result.failure().category == "internal_error"
