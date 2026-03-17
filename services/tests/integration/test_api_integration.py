"""Integration tests for API with real use cases and in-memory repositories."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from application.dtos.artifact_dtos import ArtifactResponse
from application.dtos.page_dtos import PageResponse
from application.ports.repositories.artifact_read_models import ArtifactReadModel
from application.ports.repositories.page_read_models import PageReadModel
from application.use_cases.artifact_use_cases import (
    CreateArtifactUseCase,
    UpdateTitleMentionUseCase,
)
from application.use_cases.page_use_cases import AddCompoundMentionsUseCase, CreatePageUseCase
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from interfaces.api.main import app
from interfaces.dependencies import get_auth, get_container
from sentinel_auth.authz_middleware import AuthzMiddleware
from tests.fakes.fake_auth import FakeAuth
from tests.mocks import MockArtifactRepository, MockPageRepository


class SimpleContainer:
    def __init__(self, mapping: dict[type, object]) -> None:
        self._mapping = mapping

    def __getitem__(self, key: type) -> object:
        return self._mapping[key]


class RepoBackedArtifactReadModel:
    """Thin read model adapter that wraps MockArtifactRepository for integration tests."""

    def __init__(self, repo: MockArtifactRepository) -> None:
        self._repo = repo

    async def get_artifact_by_id(self, artifact_id: UUID, workspace_id: UUID | None = None) -> ArtifactResponse | None:
        try:
            a = self._repo.get_by_id(artifact_id)
        except Exception:
            return None
        return ArtifactResponse(
            artifact_id=a.id,
            source_uri=a.source_uri,
            source_filename=a.source_filename,
            artifact_type=a.artifact_type,
            mime_type=a.mime_type,
            storage_location=a.storage_location,
            workspace_id=a.workspace_id,
            owner_id=a.owner_id,
        )

    async def list_artifacts(self, workspace_id: UUID | None = None, skip: int = 0, limit: int = 100, allowed_artifact_ids: list[UUID] | None = None) -> list:
        return []


class RepoBackedPageReadModel:
    """Thin read model adapter that wraps MockPageRepository for integration tests."""

    def __init__(self, repo: MockPageRepository) -> None:
        self._repo = repo

    async def get_page_by_id(self, page_id: UUID, workspace_id: UUID | None = None) -> PageResponse | None:
        try:
            p = self._repo.get_by_id(page_id)
        except Exception:
            return None
        return PageResponse(
            page_id=p.id,
            artifact_id=p.artifact_id,
            name=p.name,
            index=p.index,
            compound_mentions=[],
            tag_mentions=[],
            workspace_id=p.workspace_id,
            owner_id=p.owner_id,
        )

    async def get_pages_by_id(self, page_ids: list[UUID], workspace_id: UUID | None = None) -> list:
        return []


def _strip_authz_middleware() -> None:
    """Remove AuthzMiddleware from the app so tests can run without tokens."""
    app.user_middleware = [m for m in app.user_middleware if m.cls is not AuthzMiddleware]
    # Rebuild the middleware stack
    app.middleware_stack = app.build_middleware_stack()


@pytest.fixture
def client() -> Callable[[dict[type, object]], TestClient]:
    _strip_authz_middleware()
    fake_auth = FakeAuth(role="editor")

    def _client(overrides: dict[type, object]) -> TestClient:
        container = SimpleContainer(overrides)
        app.dependency_overrides[get_container] = lambda: container
        app.dependency_overrides[get_auth] = lambda: fake_auth
        return TestClient(app)

    yield _client
    app.dependency_overrides.clear()


def _build_use_cases() -> tuple[dict[type, object], MockArtifactRepository, MockPageRepository]:
    artifact_repo = MockArtifactRepository()
    page_repo = MockPageRepository()

    use_cases: dict[type, object] = {
        CreateArtifactUseCase: CreateArtifactUseCase(artifact_repo),
        UpdateTitleMentionUseCase: UpdateTitleMentionUseCase(artifact_repo),
        CreatePageUseCase: CreatePageUseCase(page_repo, artifact_repo),
        AddCompoundMentionsUseCase: AddCompoundMentionsUseCase(page_repo),
        ArtifactReadModel: RepoBackedArtifactReadModel(artifact_repo),
        PageReadModel: RepoBackedPageReadModel(page_repo),
    }

    return use_cases, artifact_repo, page_repo


def test_create_artifact_and_update_title_mention(client) -> None:
    use_cases, artifact_repo, _ = _build_use_cases()
    api = client(use_cases)

    create_payload = {
        "source_uri": "https://example.com/paper.pdf",
        "source_filename": "paper.pdf",
        "artifact_type": ArtifactType.RESEARCH_ARTICLE,
        "mime_type": MimeType.PDF,
        "storage_location": "/storage/paper.pdf",
    }

    create_response = api.post("/artifacts/", json=create_payload)
    assert create_response.status_code == 201
    artifact_id = UUID(create_response.json()["artifact_id"])

    # ensure the artifact exists in repo
    assert artifact_repo.get_by_id(artifact_id).source_filename == "paper.pdf"

    update_response = api.patch(
        f"/artifacts/{artifact_id}/title_mention",
        json={"title": "Important Paper", "confidence": 0.95},
    )
    assert update_response.status_code == 200
    assert update_response.json()["title_mention"]["title"] == "Important Paper"


def test_create_page_and_add_compound_mentions(client) -> None:
    use_cases, artifact_repo, page_repo = _build_use_cases()
    api = client(use_cases)

    create_artifact = {
        "source_uri": "https://example.com/paper.pdf",
        "source_filename": "paper.pdf",
        "artifact_type": ArtifactType.RESEARCH_ARTICLE,
        "mime_type": MimeType.PDF,
        "storage_location": "/storage/paper.pdf",
    }
    artifact_response = api.post("/artifacts/", json=create_artifact)
    artifact_id = artifact_response.json()["artifact_id"]

    create_page_payload = {
        "artifact_id": artifact_id,
        "name": "Introduction",
        "index": 0,
    }
    page_response = api.post("/pages/", json=create_page_payload)
    assert page_response.status_code == 201
    page_id = page_response.json()["page_id"]

    # Ensure both repos updated
    assert page_repo.get_by_id(UUID(page_id)).name == "Introduction"
    # Note: Page is created but not automatically added to artifact.
    # That would require an explicit add_pages call via the use case.
    assert artifact_repo.get_by_id(UUID(artifact_id)).pages == ()

    compound_payload = {
        "page_id": page_id,
        "compound_mentions": [
            {"smiles": "C1=CC=CC=C1", "extracted_id": "Benzene"},
        ],
    }
    compound_response = api.post(
        f"/pages/{page_id}/compound_mentions",
        json=compound_payload,
    )
    assert compound_response.status_code == 200
    data = compound_response.json()
    assert len(data["compound_mentions"]) == 1
    assert data["compound_mentions"][0]["smiles"] == "C1=CC=CC=C1"
