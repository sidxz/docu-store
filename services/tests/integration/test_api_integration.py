"""Integration tests for API with real use cases and in-memory repositories."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from application.use_cases.artifact_use_cases import (
    CreateArtifactUseCase,
    UpdateTitleMentionUseCase,
)
from application.use_cases.page_use_cases import AddCompoundMentionsUseCase, CreatePageUseCase
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from interfaces.api.main import app
from interfaces.dependencies import get_container
from tests.mocks import MockArtifactRepository, MockPageRepository


class SimpleContainer:
    def __init__(self, mapping: dict[type, object]) -> None:
        self._mapping = mapping

    def __getitem__(self, key: type) -> object:
        return self._mapping[key]


@pytest.fixture
def client() -> Callable[[dict[type, object]], TestClient]:
    def _client(overrides: dict[type, object]) -> TestClient:
        container = SimpleContainer(overrides)
        app.dependency_overrides[get_container] = lambda: container
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
    assert artifact_repo.get_by_id(UUID(artifact_id)).pages == (UUID(page_id),)

    compound_payload = {
        "page_id": page_id,
        "compound_mentions": [
            {"smiles": "C1=CC=CC=C1", "extracted_name": "Benzene"},
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
