"""Tests for authorization checks across use cases."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.artifact_dtos import CreateArtifactRequest
from application.dtos.page_dtos import CreatePageRequest
from application.use_cases.artifact_use_cases import (
    AddPagesUseCase,
    CreateArtifactUseCase,
    DeleteArtifactUseCase,
    UpdateTagMentionsUseCase,
    UpdateTitleMentionUseCase,
)
from application.use_cases.page_use_cases import (
    CreatePageUseCase,
    UpdateTextMentionUseCase,
)
from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.tag_mention import TagMention
from domain.value_objects.mime_type import MimeType
from domain.value_objects.text_mention import TextMention
from domain.value_objects.title_mention import TitleMention
from tests.fakes.fake_auth import FakeAuth
from tests.mocks import MockArtifactRepository, MockPageRepository


def _create_artifact(workspace_id: UUID | None = None, owner_id: UUID | None = None) -> Artifact:
    return Artifact.create(
        source_uri="https://example.com/paper.pdf",
        source_filename="paper.pdf",
        artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF,
        storage_location="/storage/paper.pdf",
        workspace_id=workspace_id,
        owner_id=owner_id,
    )


# ---------------------------------------------------------------------------
# Role-based access
# ---------------------------------------------------------------------------


class TestRoleBasedAccess:
    """Test that viewer role is rejected on write operations."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_artifact(self) -> None:
        auth = FakeAuth(role="viewer")
        use_case = CreateArtifactUseCase(MockArtifactRepository())
        request = CreateArtifactRequest(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        result = await use_case.execute(request, auth=auth)

        assert isinstance(result, Failure)
        assert result.failure().category == "forbidden"

    @pytest.mark.asyncio
    async def test_editor_can_create_artifact(self) -> None:
        auth = FakeAuth(role="editor")
        use_case = CreateArtifactUseCase(MockArtifactRepository())
        request = CreateArtifactRequest(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        result = await use_case.execute(request, auth=auth)

        assert isinstance(result, Success)
        response = result.unwrap()
        assert response.workspace_id == auth.workspace_id
        assert response.owner_id == auth.user_id

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete_artifact(self) -> None:
        auth = FakeAuth(role="viewer")
        workspace_id = auth.workspace_id
        artifact = _create_artifact(workspace_id=workspace_id)
        repo = MockArtifactRepository()
        repo.save(artifact)

        use_case = DeleteArtifactUseCase(repo, MockPageRepository())
        result = await use_case.execute(artifact.id, auth=auth)

        assert isinstance(result, Failure)
        assert result.failure().category == "forbidden"

    @pytest.mark.asyncio
    async def test_viewer_cannot_update_tags(self) -> None:
        auth = FakeAuth(role="viewer")
        artifact = _create_artifact(workspace_id=auth.workspace_id)
        repo = MockArtifactRepository()
        repo.save(artifact)

        use_case = UpdateTagMentionsUseCase(repo)
        tag = TagMention(tag="tag", confidence=0.9)
        result = await use_case.execute(artifact.id, [tag], auth=auth)

        assert isinstance(result, Failure)
        assert result.failure().category == "forbidden"

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_page(self) -> None:
        auth = FakeAuth(role="viewer")
        artifact = _create_artifact(workspace_id=auth.workspace_id)
        artifact_repo = MockArtifactRepository()
        artifact_repo.save(artifact)

        use_case = CreatePageUseCase(MockPageRepository(), artifact_repo)
        request = CreatePageRequest(name="Page 1", artifact_id=artifact.id, index=0)

        result = await use_case.execute(request, auth=auth)

        assert isinstance(result, Failure)
        assert result.failure().category == "forbidden"


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------


class TestWorkspaceIsolation:
    """Test that users cannot access artifacts from other workspaces."""

    @pytest.mark.asyncio
    async def test_cannot_delete_artifact_in_other_workspace(self) -> None:
        workspace_a = uuid4()
        workspace_b = uuid4()
        auth = FakeAuth(role="editor", workspace_id=workspace_b)

        artifact = _create_artifact(workspace_id=workspace_a)
        repo = MockArtifactRepository()
        repo.save(artifact)

        use_case = DeleteArtifactUseCase(repo, MockPageRepository())
        result = await use_case.execute(artifact.id, auth=auth)

        # Returns not_found (not forbidden) to avoid leaking existence
        assert isinstance(result, Failure)
        assert result.failure().category == "not_found"

    @pytest.mark.asyncio
    async def test_cannot_update_title_in_other_workspace(self) -> None:
        workspace_a = uuid4()
        auth = FakeAuth(role="editor", workspace_id=uuid4())

        artifact = _create_artifact(workspace_id=workspace_a)
        repo = MockArtifactRepository()
        repo.save(artifact)

        use_case = UpdateTitleMentionUseCase(repo)
        result = await use_case.execute(
            artifact.id,
            TitleMention(title="new", confidence=0.9),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert result.failure().category == "not_found"

    @pytest.mark.asyncio
    async def test_cannot_update_text_mention_in_other_workspace(self) -> None:
        workspace_a = uuid4()
        auth = FakeAuth(role="editor", workspace_id=uuid4())

        page = Page.create(
            name="Page 1",
            artifact_id=uuid4(),
            index=0,
            workspace_id=workspace_a,
        )
        repo = MockPageRepository()
        repo.save(page)

        use_case = UpdateTextMentionUseCase(repo)
        result = await use_case.execute(
            page.id,
            TextMention(text="text", confidence=0.9),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert result.failure().category == "not_found"

    @pytest.mark.asyncio
    async def test_can_update_artifact_in_same_workspace(self) -> None:
        workspace_id = uuid4()
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

        artifact = _create_artifact(workspace_id=workspace_id)
        repo = MockArtifactRepository()
        repo.save(artifact)

        use_case = UpdateTagMentionsUseCase(repo)
        tag = TagMention(tag="tag1", confidence=0.9)
        result = await use_case.execute(artifact.id, [tag], auth=auth)

        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_can_add_pages_in_same_workspace(self) -> None:
        workspace_id = uuid4()
        auth = FakeAuth(role="editor", workspace_id=workspace_id)

        artifact = _create_artifact(workspace_id=workspace_id)
        artifact_repo = MockArtifactRepository()
        artifact_repo.save(artifact)

        page = Page.create(
            name="Page 1",
            artifact_id=artifact.id,
            index=0,
            workspace_id=workspace_id,
        )
        page_repo = MockPageRepository()
        page_repo.save(page)

        use_case = AddPagesUseCase(artifact_repo, page_repo)
        result = await use_case.execute(artifact.id, [page.id], auth=auth)

        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_cannot_add_pages_in_other_workspace(self) -> None:
        workspace_a = uuid4()
        auth = FakeAuth(role="editor", workspace_id=uuid4())

        artifact = _create_artifact(workspace_id=workspace_a)
        artifact_repo = MockArtifactRepository()
        artifact_repo.save(artifact)

        use_case = AddPagesUseCase(artifact_repo, MockPageRepository())
        result = await use_case.execute(artifact.id, [uuid4()], auth=auth)

        assert isinstance(result, Failure)
        assert result.failure().category == "not_found"


# ---------------------------------------------------------------------------
# No-auth backwards compat (Temporal workers call without auth)
# ---------------------------------------------------------------------------


class TestNoAuthBackwardsCompat:
    """Test that use cases still work without auth (for Temporal workers)."""

    @pytest.mark.asyncio
    async def test_create_artifact_without_auth(self) -> None:
        use_case = CreateArtifactUseCase(MockArtifactRepository())
        request = CreateArtifactRequest(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )

        result = await use_case.execute(request)

        assert isinstance(result, Success)
        response = result.unwrap()
        assert response.workspace_id is None
        assert response.owner_id is None

    @pytest.mark.asyncio
    async def test_delete_artifact_without_auth(self) -> None:
        artifact = _create_artifact()
        repo = MockArtifactRepository()
        repo.save(artifact)

        use_case = DeleteArtifactUseCase(repo, MockPageRepository())
        result = await use_case.execute(artifact.id)

        assert isinstance(result, Success)
