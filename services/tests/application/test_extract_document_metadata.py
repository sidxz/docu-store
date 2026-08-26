from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from application.use_cases.extract_document_metadata_use_case import (
    ExtractDocumentMetadataUseCase,
)
from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.author_mention import AuthorMention
from domain.value_objects.mime_type import MimeType
from domain.value_objects.presentation_date import PresentationDate
from domain.value_objects.text_mention import TextMention
from domain.value_objects.title_mention import TitleMention
from tests.mocks import (
    MockArtifactRepository,
    MockExternalEventPublisher,
    MockPageRepository,
)


class _StubPromptRepo:
    async def render_prompt(self, name: str, **kwargs: str) -> str:  # noqa: ARG002
        return "rendered prompt"


class _StubLLM:
    def __init__(self) -> None:
        self.schema: dict | None = None

    async def complete_structured(self, prompt: str, schema: dict, **kwargs) -> dict:  # noqa: ANN003, ARG002
        self.schema = schema
        return {"title": "Inhibitor study", "authors": [{"name": "A. Smith"}], "date": "2024"}


@pytest.mark.asyncio
async def test_llm_extract_uses_structured_output() -> None:
    # Construct without __init__ — _llm_extract only touches these two deps.
    uc = object.__new__(ExtractDocumentMetadataUseCase)
    uc.prompt_repository = _StubPromptRepo()
    uc.llm_client = _StubLLM()

    out = await uc._llm_extract("some page text")

    assert out == {"title": "Inhibitor study", "authors": [{"name": "A. Smith"}], "date": "2024"}
    # Passed a JSON-schema dict (not a free-text "respond in JSON" prompt).
    assert uc.llm_client.schema["type"] == "object"
    assert "authors" in uc.llm_client.schema["properties"]


@pytest.mark.asyncio
async def test_llm_extract_propagates_errors() -> None:
    from domain.exceptions import LLMAuthError

    class _Boom:
        async def complete_structured(self, *a, **k):  # noqa: ANN002, ANN003
            raise LLMAuthError("401")

    uc = object.__new__(ExtractDocumentMetadataUseCase)
    uc.prompt_repository = _StubPromptRepo()
    uc.llm_client = _Boom()

    with pytest.raises(LLMAuthError):
        await uc._llm_extract("text")


# ── Fully human-corrected artifact must not be overwritten by extraction ──


class _NullCtx:
    def __enter__(self) -> str:
        return "/fake/render.pdf"

    def __exit__(self, *_a: object) -> bool:
        return False


class _StubBlob:
    def get_file(self, _key: str) -> _NullCtx:
        return _NullCtx()


class _StubTitleExtractor:
    def extract_title(self, _path: str, _index: int) -> SimpleNamespace:
        return SimpleNamespace(title="Extracted Title", confidence=0.9)


class _StubExtractor:
    async def extract(self, _text: str, _schema: list[str], *, threshold: float = 0.3) -> list:  # noqa: ARG002
        return [
            SimpleNamespace(name="author_name", value="Bob Jones", score=0.9),
            SimpleNamespace(name="presentation_date", value="2024-01-15", score=0.9),
        ]


@pytest.mark.asyncio
async def test_fully_corrected_artifact_not_overwritten() -> None:
    """Extraction yields title/authors/date, but all three are human-corrected → no save, no notify."""
    page = Page.create(name="Page 1", artifact_id=uuid4(), index=0)
    page.update_text_mention(TextMention(text="Bob Jones presented on 2024-01-15.", confidence=0.9))
    page_repo = MockPageRepository()
    page_repo.save(page)

    artifact = Artifact.create(
        source_uri=None,
        source_filename="deck.pdf",
        artifact_type=ArtifactType.SCIENTIFIC_PRESENTATION,
        mime_type=MimeType.PDF,
        storage_location="blobs/deck.pdf",
    )
    artifact.add_pages([page.id])
    artifact.correct_metadata(
        corrected_by_id="u1",
        corrected_by_name="Human",
        title_mention=TitleMention(title="Human Title"),
        author_mentions=[AuthorMention(name="Human Author")],
        presentation_date=PresentationDate(date=datetime(2020, 1, 1, tzinfo=UTC)),
    )
    repo = MockArtifactRepository()
    repo.save(artifact)
    repo.save_called = False  # reset after seeding

    publisher = MockExternalEventPublisher()
    uc = object.__new__(ExtractDocumentMetadataUseCase)
    uc.artifact_repository = repo
    uc.page_repository = page_repo
    uc.structured_extractor = _StubExtractor()
    uc.title_extractor = _StubTitleExtractor()
    uc.blob_store = _StubBlob()
    uc.llm_client = _StubLLM()  # unused: extraction completes before LLM fallback
    uc.prompt_repository = _StubPromptRepo()
    uc.external_event_publisher = publisher
    uc.token_usage_store = None

    result = await uc.execute(artifact.id, page.id)

    assert result.unwrap()["status"] == "success"
    assert repo.save_called is False  # human corrections untouched
    assert publisher.artifact_updated_called is False  # no misleading DocumentMetadataUpdated
    # Sanity: the human values survived.
    assert repo.get_by_id(artifact.id).title_mention.title == "Human Title"


# ── Fields found before the LLM lane survive an LLM failure (Phase 3 fold-in) ──


class _NoTitle:
    def extract_title(self, _path: str, _index: int) -> None:
        return None


class _BoomLLM:
    async def complete_structured(self, prompt: str, schema: dict, **kwargs) -> dict:  # noqa: ANN003, ARG002
        from domain.exceptions import LLMAuthError

        raise LLMAuthError("The provider rejected the key (401).")


def _incomplete_setup(llm):  # noqa: ANN001
    page = Page.create(name="Page 1", artifact_id=uuid4(), index=0)
    page.update_text_mention(TextMention(text="Bob Jones presented on 2024-01-15.", confidence=0.9))
    page_repo = MockPageRepository()
    page_repo.save(page)
    artifact = Artifact.create(
        source_uri=None,
        source_filename="deck.pdf",
        artifact_type=ArtifactType.SCIENTIFIC_PRESENTATION,
        mime_type=MimeType.PDF,
        storage_location="blobs/deck.pdf",
    )
    artifact.add_pages([page.id])
    repo = MockArtifactRepository()
    repo.save(artifact)
    repo.save_called = False
    publisher = MockExternalEventPublisher()
    uc = object.__new__(ExtractDocumentMetadataUseCase)
    uc.artifact_repository = repo
    uc.page_repository = page_repo
    uc.structured_extractor = _StubExtractor()  # authors + date, no title → LLM runs
    uc.title_extractor = _NoTitle()
    uc.blob_store = _StubBlob()
    uc.llm_client = llm
    uc.prompt_repository = _StubPromptRepo()
    uc.external_event_publisher = publisher
    uc.token_usage_store = None
    uc.llm_scope = None
    return uc, artifact, page, repo, publisher


@pytest.mark.asyncio
async def test_gliner_fields_persist_before_a_failing_llm_fallback() -> None:
    from domain.exceptions import LLMAuthError

    uc, artifact, page, repo, publisher = _incomplete_setup(_BoomLLM())

    with pytest.raises(LLMAuthError):
        await uc.execute(artifact.id, page.id)

    saved = repo.get_by_id(artifact.id)
    assert repo.save_called is True
    assert [a.name for a in saved.author_mentions] == ["Bob Jones"]
    assert saved.presentation_date is not None
    assert saved.title_mention is None  # the LLM never delivered one
    assert publisher.artifact_updated_called is True


@pytest.mark.asyncio
async def test_llm_fills_only_missing_fields_after_the_first_persist() -> None:
    uc, artifact, page, repo, _ = _incomplete_setup(_StubLLM())

    result = await uc.execute(artifact.id, page.id)

    assert result.unwrap()["status"] == "success"
    saved = repo.get_by_id(artifact.id)
    assert saved.title_mention.title == "Inhibitor study"  # from the LLM
    assert saved.title_mention.model_name == "llm-fallback"
    assert [a.name for a in saved.author_mentions] == ["Bob Jones"]  # GLiNER kept, not "A. Smith"
    assert saved.presentation_date.date.year == 2024
