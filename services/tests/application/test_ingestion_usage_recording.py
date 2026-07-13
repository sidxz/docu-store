"""Ingestion-side token accounting: enrichment LLM calls must land on the ledger,
attributed to the uploading user via the Artifact aggregate."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from returns.result import Failure, Success

from application.use_cases.summarization_use_cases import SummarizePageUseCase
from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from domain.value_objects.text_mention import TextMention
from tests.mocks import (
    MockArtifactRepository,
    MockBlobStore,
    MockLLMClient,
    MockPageRepository,
    MockPromptRepository,
)

_LONG_TEXT = "A" * 101


class FakeUsageStore:
    def __init__(self) -> None:
        self.events = []

    async def record(self, event) -> None:
        self.events.append(event)


def _setup(owner_id: UUID, workspace_id: UUID, *, usage=(300, 40)):
    artifact = Artifact.create(
        source_uri=None,
        source_filename="slides.pdf",
        artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF,
        storage_location="/storage/slides.pdf",
        workspace_id=workspace_id,
        owner_id=owner_id,
    )
    page = Page.create(name="Slide 1", artifact_id=artifact.id, index=0)
    page.update_text_mention(TextMention(text=_LONG_TEXT))

    artifact_repo = MockArtifactRepository()
    artifact_repo.artifacts[artifact.id] = artifact
    page_repo = MockPageRepository()
    page_repo.pages[page.id] = page

    store = FakeUsageStore()
    use_case = SummarizePageUseCase(
        page_repository=page_repo,
        artifact_repository=artifact_repo,
        llm_client=MockLLMClient(response="Summary.", usage=usage),
        prompt_repository=MockPromptRepository(),
        blob_store=MockBlobStore(exists_result=True, bytes_result=b"png-bytes"),
        external_event_publisher=None,
        token_usage_store=store,
    )
    return use_case, page, artifact, store


@pytest.mark.asyncio
async def test_page_summary_records_attributed_ingestion_event() -> None:
    owner, ws = uuid4(), uuid4()
    use_case, page, artifact, store = _setup(owner, ws)

    result = await use_case.execute(page.id)

    assert isinstance(result, Success)
    assert len(store.events) == 1
    ev = store.events[0]
    assert (ev.kind, ev.source) == ("ingestion", "page_summary")
    assert (ev.user_id, ev.workspace_id) == (owner, ws)
    assert (ev.prompt, ev.completion, ev.total) == (300, 40, 340)
    assert ev.ref == str(page.id)
    assert ev.event_id is None  # retries append, never dedupe


@pytest.mark.asyncio
async def test_zero_usage_records_nothing() -> None:
    use_case, page, artifact, store = _setup(uuid4(), uuid4(), usage=None)
    result = await use_case.execute(page.id)
    assert isinstance(result, Success)
    assert store.events == []


@pytest.mark.asyncio
async def test_no_store_is_a_harmless_noop() -> None:
    owner, ws = uuid4(), uuid4()
    use_case, page, artifact, store = _setup(owner, ws)
    use_case.token_usage_store = None
    result = await use_case.execute(page.id)
    assert isinstance(result, Success)


@pytest.mark.asyncio
async def test_llm_failure_after_usage_still_records_partial() -> None:
    """A run that dies after the provider reported usage (e.g. a later call in
    a multi-call chain fails) must still land its partial spend on the ledger."""
    owner, ws = uuid4(), uuid4()
    use_case, page, artifact, store = _setup(owner, ws)

    class _RecordThenFailLLM(MockLLMClient):
        async def complete_with_image(self, prompt: str, image_b64: str, **kwargs):
            self._record()  # provider reported usage…
            raise RuntimeError("…then the run died")

    use_case.llm_client = _RecordThenFailLLM(usage=(50, 0))

    result = await use_case.execute(page.id)

    assert isinstance(result, Failure)  # use case maps the error as before
    assert len(store.events) == 1  # …but the spend was recorded by the finally
    assert (store.events[0].prompt, store.events[0].total) == (50, 50)
