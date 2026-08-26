"""Ingestion use cases resolve the uploader's LLM config around their LLM calls
and let typed LLM errors escape (the activity decides retry vs. fail)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from application.ports.user_llm_config import UserLLMConfig
from application.services.llm_scope import UserLLMScope
from application.use_cases.extract_page_entities_use_case import ExtractPageEntitiesUseCase
from application.use_cases.summarization_use_cases import (
    SummarizeArtifactUseCase,
    SummarizePageUseCase,
)
from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.exceptions import LLMAuthError, LLMNotConfiguredError, LLMRateLimitedError
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from domain.value_objects.summary_candidate import SummaryCandidate
from domain.value_objects.text_mention import TextMention
from infrastructure.llm.llm_context import get_user_config
from tests.mocks import (
    MockArtifactRepository,
    MockBlobStore,
    MockLLMClient,
    MockPageRepository,
    MockPromptRepository,
)

WS, OWNER = uuid4(), uuid4()
CFG = UserLLMConfig(provider="openai", api_key="k")


class _Store:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, UUID]] = []

    async def get(self, workspace_id: UUID, user_id: UUID) -> UserLLMConfig | None:
        self.calls.append((workspace_id, user_id))
        return CFG


class _SeeingLLM(MockLLMClient):
    """Records the user config visible at call time."""

    def __init__(self) -> None:
        super().__init__(response="summary")
        self.seen: list[UserLLMConfig | None] = []

    async def complete(self, prompt: str, **kwargs):  # noqa: ANN003, ANN202
        self.seen.append(get_user_config())
        return await super().complete(prompt, **kwargs)

    async def complete_with_image(self, prompt: str, image_b64: str, **kwargs):  # noqa: ANN003, ANN202
        self.seen.append(get_user_config())
        return await super().complete_with_image(prompt, image_b64, **kwargs)


def _artifact() -> Artifact:
    return Artifact.create(
        source_uri=None, source_filename="s.pdf", artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF, storage_location="/s.pdf", workspace_id=WS, owner_id=OWNER,
    )


def _repos(artifact: Artifact, *pages: Page):
    artifact_repo = MockArtifactRepository()
    artifact_repo.artifacts[artifact.id] = artifact
    page_repo = MockPageRepository()
    for p in pages:
        page_repo.pages[p.id] = p
    return artifact_repo, page_repo


def _page_use_case(llm, scope=None):
    artifact = _artifact()
    page = Page.create(name="Slide 1", artifact_id=artifact.id, index=0)
    page.update_text_mention(TextMention(text="x" * 200))
    artifact_repo, page_repo = _repos(artifact, page)
    uc = SummarizePageUseCase(
        page_repository=page_repo, artifact_repository=artifact_repo, llm_client=llm,
        prompt_repository=MockPromptRepository(), blob_store=MockBlobStore(exists_result=False),
        llm_scope=scope,
    )
    return uc, page


async def test_summarize_page_resolves_owner_config_around_llm_calls() -> None:
    store, llm = _Store(), _SeeingLLM()
    uc, page = _page_use_case(llm, UserLLMScope(store, enabled=True))
    await uc.execute(page.id)
    assert store.calls == [(WS, OWNER)]
    assert llm.seen == [CFG]
    assert get_user_config() is None


@pytest.mark.parametrize("exc", [LLMAuthError("401"), LLMNotConfiguredError("no key"), LLMRateLimitedError("429")])
async def test_summarize_page_lets_llm_errors_escape_and_resets_scope(exc) -> None:
    store = _Store()
    uc, page = _page_use_case(MockLLMClient(raise_on_call=exc), UserLLMScope(store, enabled=True))
    with pytest.raises(type(exc)):
        await uc.execute(page.id)
    assert store.calls == [(WS, OWNER)]
    assert get_user_config() is None  # scope reset even though the LLM raised


async def test_summarize_page_still_wraps_unknown_errors() -> None:
    from returns.result import Failure

    uc, page = _page_use_case(MockLLMClient(raise_on_call=RuntimeError("ollama down")))
    result = await uc.execute(page.id)
    assert isinstance(result, Failure)
    assert result.failure().category == "internal_error"


def _artifact_use_case(llm, scope=None):
    artifact = _artifact()
    page = Page.create(name="Slide 1", artifact_id=artifact.id, index=0)
    page.update_summary_candidate(SummaryCandidate(summary="page summary"))  # all other fields optional
    artifact.add_pages([page.id])
    artifact_repo, page_repo = _repos(artifact, page)
    uc = SummarizeArtifactUseCase(
        artifact_repository=artifact_repo, page_repository=page_repo, llm_client=llm,
        prompt_repository=MockPromptRepository(), llm_scope=scope,
    )
    return uc, artifact


async def test_summarize_artifact_resolves_owner_config() -> None:
    store, llm = _Store(), _SeeingLLM()
    uc, artifact = _artifact_use_case(llm, UserLLMScope(store, enabled=True))
    await uc.execute(artifact.id)
    assert store.calls == [(WS, OWNER)]
    assert llm.seen and all(s is CFG for s in llm.seen)


async def test_summarize_artifact_lets_llm_errors_escape() -> None:
    uc, artifact = _artifact_use_case(MockLLMClient(raise_on_call=LLMAuthError("402")))
    with pytest.raises(LLMAuthError):
        await uc.execute(artifact.id)


class _NER:
    def __init__(self, exc: Exception | None = None) -> None:
        self.exc = exc
        self.seen: list[UserLLMConfig | None] = []

    async def extract(self, text: str):  # noqa: ANN202
        self.seen.append(get_user_config())
        if self.exc:
            raise self.exc
        return []


def _ner_use_case(ner, scope=None):
    artifact = _artifact()
    page = Page.create(name="Slide 1", artifact_id=artifact.id, index=0)
    page.update_text_mention(TextMention(text="EGFR inhibitor"))
    artifact_repo, page_repo = _repos(artifact, page)
    uc = ExtractPageEntitiesUseCase(
        page_repository=page_repo, artifact_repository=artifact_repo, ner_extractor=ner, llm_scope=scope,
    )
    return uc, page


async def test_extract_page_entities_resolves_owner_config_and_propagates() -> None:
    store, ner = _Store(), _NER()
    uc, page = _ner_use_case(ner, UserLLMScope(store, enabled=True))
    await uc.execute(page.id)
    assert store.calls == [(WS, OWNER)]
    assert ner.seen == [CFG]

    uc, page = _ner_use_case(_NER(LLMNotConfiguredError("no key")))
    with pytest.raises(LLMNotConfiguredError):
        await uc.execute(page.id)
