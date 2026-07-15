"""Tests for CorrectArtifactMetadataUseCase (hiledit human-in-the-loop corrections)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.correction_dtos import CorrectArtifactMetadataRequest, CorrectedTagInput
from application.use_cases.correct_metadata_use_cases import CorrectArtifactMetadataUseCase
from domain.aggregates.artifact import Artifact
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.author_mention import AuthorMention
from domain.value_objects.mime_type import MimeType
from domain.value_objects.presentation_date import PresentationDate
from domain.value_objects.tag_mention import TagMention, TagSource
from domain.value_objects.title_mention import TitleMention
from tests.fakes.fake_auth import FakeAuth
from tests.mocks import MockArtifactRepository

# ---------------------------------------------------------------------------
# Local fixtures — no existing conftest fixture matches this shape, so these
# mirror the fixture style already used across tests/application (MockArtifactRepository
# from tests.mocks, FakeAuth from tests.fakes.fake_auth).
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_artifact_repo() -> MockArtifactRepository:
    return MockArtifactRepository()


@pytest.fixture
def auth_editor() -> FakeAuth:
    return FakeAuth(role="editor", name="Jane Reviewer", email="jane.reviewer@example.com")


@pytest.fixture
def make_saved_artifact(fake_artifact_repo: MockArtifactRepository):
    """Factory: build + save an Artifact, optionally pre-seeded with machine mentions."""

    def _make(
        *,
        with_title: bool = False,
        with_date: bool = False,
        tags: list[TagMention] | None = None,
        authors: list[AuthorMention] | None = None,
    ) -> Artifact:
        artifact = Artifact.create(
            source_uri=None,
            source_filename="deck.pdf",
            artifact_type=ArtifactType.SCIENTIFIC_PRESENTATION,
            mime_type=MimeType.PDF,
            storage_location="blobs/deck.pdf",
        )
        if with_title:
            artifact.update_title_mention(TitleMention(title="Original Title"))
        if with_date:
            artifact.update_presentation_date(
                PresentationDate(date=datetime(2020, 1, 1, tzinfo=UTC)),
            )
        if tags:
            artifact.update_tag_mentions(tags)
        if authors:
            artifact.update_author_mentions(authors)
        fake_artifact_repo.save(artifact)
        return artifact

    return _make


class TestCorrectArtifactMetadataUseCase:
    """Test CorrectArtifactMetadataUseCase — human corrections to artifact metadata."""

    @pytest.mark.asyncio
    async def test_corrects_title_and_records_actor(
        self,
        fake_artifact_repo: MockArtifactRepository,
        make_saved_artifact,
        auth_editor: FakeAuth,
    ) -> None:
        """A title correction updates the mention and stamps who corrected it."""
        artifact = make_saved_artifact()
        uc = CorrectArtifactMetadataUseCase(artifact_repository=fake_artifact_repo)

        result = await uc.execute(
            artifact_id=artifact.id,
            request=CorrectArtifactMetadataRequest(title="Fixed Title"),
            auth=auth_editor,
        )

        assert isinstance(result, Success)
        saved = fake_artifact_repo.get_by_id(artifact.id)
        assert saved.title_mention.title == "Fixed Title"
        assert saved.human_corrections["title_mention"]["corrected_by_id"] == str(
            auth_editor.user_id
        )
        assert saved.human_corrections["title_mention"]["corrected_by_name"] == auth_editor.name
        assert result.unwrap().human_corrections["title_mention"].corrected_by_id == str(
            auth_editor.user_id
        )

    @pytest.mark.asyncio
    async def test_omitted_fields_untouched_null_clears(
        self,
        fake_artifact_repo: MockArtifactRepository,
        make_saved_artifact,
        auth_editor: FakeAuth,
    ) -> None:
        """Explicit null clears a field; fields absent from the request are left alone."""
        artifact = make_saved_artifact(with_date=True, with_title=True)
        uc = CorrectArtifactMetadataUseCase(artifact_repository=fake_artifact_repo)

        await uc.execute(
            artifact_id=artifact.id,
            request=CorrectArtifactMetadataRequest(presentation_date=None),  # explicit null
            auth=auth_editor,
        )

        saved = fake_artifact_repo.get_by_id(artifact.id)
        assert saved.presentation_date is None  # cleared
        assert saved.title_mention is not None  # untouched (omitted)
        assert list(saved.human_corrections) == ["presentation_date"]

    @pytest.mark.asyncio
    async def test_tag_merge_preserves_existing_rich_mentions(
        self,
        fake_artifact_repo: MockArtifactRepository,
        make_saved_artifact,
        auth_editor: FakeAuth,
    ) -> None:
        """Retained tags keep their provenance; new tags get a fresh mention."""
        rich = TagMention(
            tag="Rho Kinase",
            entity_type="target",
            tag_normalized="rhokinase",
            sources=[TagSource(page_id=uuid4(), page_index=0, confidence=0.9)],
            max_confidence=0.9,
            page_count=1,
        )
        artifact = make_saved_artifact(tags=[rich])
        uc = CorrectArtifactMetadataUseCase(artifact_repository=fake_artifact_repo)

        await uc.execute(
            artifact_id=artifact.id,
            request=CorrectArtifactMetadataRequest(
                tags=[
                    CorrectedTagInput(
                        tag="rho kinase", entity_type="target"
                    ),  # kept → rich preserved
                    CorrectedTagInput(tag="autophagy"),  # new → fresh mention
                ],
            ),
            auth=auth_editor,
        )

        saved = fake_artifact_repo.get_by_id(artifact.id)
        assert saved.tag_mentions[0].sources == rich.sources  # provenance preserved
        assert saved.tag_mentions[1].tag == "autophagy"
        assert saved.tag_mentions[1].tag_normalized == "autophagy"

    @pytest.mark.asyncio
    async def test_author_merge_preserves_existing_rich_mentions(
        self,
        fake_artifact_repo: MockArtifactRepository,
        make_saved_artifact,
        auth_editor: FakeAuth,
    ) -> None:
        """Retained authors keep the original rich mention; new authors get a fresh one."""
        rich = AuthorMention(
            name="Jane Doe",
            confidence=0.85,
            date_extracted=datetime(2025, 1, 1, tzinfo=UTC),
        )
        artifact = make_saved_artifact(authors=[rich])
        uc = CorrectArtifactMetadataUseCase(artifact_repository=fake_artifact_repo)

        await uc.execute(
            artifact_id=artifact.id,
            request=CorrectArtifactMetadataRequest(
                authors=["  JANE doe ", "New Author"],  # kept (case/space-insensitive) + added
            ),
            auth=auth_editor,
        )

        saved = fake_artifact_repo.get_by_id(artifact.id)
        assert saved.author_mentions[0] is rich  # original rich mention preserved (identity)
        assert saved.author_mentions[0].confidence == 0.85
        assert saved.author_mentions[1].name == "New Author"
        assert saved.author_mentions[1].date_extracted is not None
        assert list(saved.human_corrections) == ["author_mentions"]

    @pytest.mark.asyncio
    async def test_date_normalized_to_utc_datetime_with_human_source(
        self,
        fake_artifact_repo: MockArtifactRepository,
        make_saved_artifact,
        auth_editor: FakeAuth,
    ) -> None:
        """A corrected date is normalized to a UTC midnight datetime with source='human'."""
        artifact = make_saved_artifact()
        uc = CorrectArtifactMetadataUseCase(artifact_repository=fake_artifact_repo)

        await uc.execute(
            artifact_id=artifact.id,
            request=CorrectArtifactMetadataRequest(presentation_date=date(2026, 3, 2)),
            auth=auth_editor,
        )

        saved = fake_artifact_repo.get_by_id(artifact.id)
        assert saved.presentation_date.date == datetime(2026, 3, 2, tzinfo=UTC)
        assert saved.presentation_date.source == "human"

    @pytest.mark.asyncio
    async def test_requires_auth(
        self,
        fake_artifact_repo: MockArtifactRepository,
        make_saved_artifact,
    ) -> None:
        """A correction with no authenticated actor is rejected outright (not a silent no-op)."""
        artifact = make_saved_artifact()
        uc = CorrectArtifactMetadataUseCase(artifact_repository=fake_artifact_repo)

        result = await uc.execute(
            artifact_id=artifact.id,
            request=CorrectArtifactMetadataRequest(title="X"),
            auth=None,
        )

        assert isinstance(result, Failure)
        assert result.failure().category == "unauthorized"

    @pytest.mark.asyncio
    async def test_empty_request_is_validation_error(
        self,
        fake_artifact_repo: MockArtifactRepository,
        make_saved_artifact,
        auth_editor: FakeAuth,
    ) -> None:
        """A request with no fields set is rejected as invalid, not a silent no-op."""
        artifact = make_saved_artifact()
        uc = CorrectArtifactMetadataUseCase(artifact_repository=fake_artifact_repo)

        result = await uc.execute(
            artifact_id=artifact.id,
            request=CorrectArtifactMetadataRequest(),
            auth=auth_editor,
        )

        assert isinstance(result, Failure)
        assert result.failure().category == "validation"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("blank", ["", "   "])
    async def test_blank_title_is_validation_error(
        self,
        fake_artifact_repo: MockArtifactRepository,
        make_saved_artifact,
        auth_editor: FakeAuth,
        blank: str,
    ) -> None:
        """An explicit blank/whitespace title is a validation error, not a clear."""
        artifact = make_saved_artifact()
        uc = CorrectArtifactMetadataUseCase(artifact_repository=fake_artifact_repo)

        result = await uc.execute(
            artifact_id=artifact.id,
            request=CorrectArtifactMetadataRequest(title=blank),
            auth=auth_editor,
        )

        assert isinstance(result, Failure)
        assert result.failure().category == "validation"

    @pytest.mark.asyncio
    async def test_title_none_clears_existing_title(
        self,
        fake_artifact_repo: MockArtifactRepository,
        make_saved_artifact,
        auth_editor: FakeAuth,
    ) -> None:
        """Explicit null title clears a previously extracted title (unlike a blank string)."""
        artifact = make_saved_artifact(with_title=True)
        uc = CorrectArtifactMetadataUseCase(artifact_repository=fake_artifact_repo)

        await uc.execute(
            artifact_id=artifact.id,
            request=CorrectArtifactMetadataRequest(title=None),
            auth=auth_editor,
        )

        saved = fake_artifact_repo.get_by_id(artifact.id)
        assert saved.title_mention is None
        assert list(saved.human_corrections) == ["title_mention"]
