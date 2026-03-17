"""Tests for API routes."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from returns.result import Failure, Success

from application.dtos.artifact_dtos import ArtifactResponse, CreateArtifactRequest
from application.dtos.errors import AppError
from application.dtos.page_dtos import AddCompoundMentionsRequest, CreatePageRequest, PageResponse
from application.ports.repositories.artifact_read_models import ArtifactReadModel
from application.ports.repositories.page_read_models import PageReadModel
from application.use_cases.artifact_use_cases import (
    CreateArtifactUseCase,
    UpdateTitleMentionUseCase,
)
from application.use_cases.page_use_cases import CreatePageUseCase, DeletePageUseCase
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from interfaces.api.main import app
from interfaces.dependencies import get_auth, get_container
from sentinel_auth.authz_middleware import AuthzMiddleware
from tests.fakes.fake_auth import FakeAuth


class FakeContainer:
    def __init__(self, mapping: dict[type, object]) -> None:
        self._mapping = mapping

    def __getitem__(self, key: type) -> object:
        return self._mapping[key]


class FakeArtifactReadModel(ArtifactReadModel):
    def __init__(self, artifacts: dict[UUID, ArtifactResponse]) -> None:
        self._artifacts = artifacts

    async def get_artifact_by_id(self, artifact_id: UUID, workspace_id: UUID | None = None) -> ArtifactResponse | None:
        return self._artifacts.get(artifact_id)

    async def list_artifacts(self, workspace_id: UUID | None = None, skip: int = 0, limit: int = 100, allowed_artifact_ids: list[UUID] | None = None) -> list[ArtifactResponse]:
        artifacts = list(self._artifacts.values())
        return artifacts[skip : skip + limit]


class FakePageReadModel(PageReadModel):
    def __init__(self, pages: dict[UUID, PageResponse]) -> None:
        self._pages = pages

    async def get_page_by_id(self, page_id: UUID, workspace_id: UUID | None = None) -> PageResponse | None:
        return self._pages.get(page_id)

    async def get_pages_by_id(self, page_ids: list[UUID], workspace_id: UUID | None = None) -> list[PageResponse]:
        return [self._pages[pid] for pid in page_ids if pid in self._pages]


class FakeUseCase:
    def __init__(self, result: object) -> None:
        self._result = result

    async def execute(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._result


def _strip_authz_middleware() -> None:
    """Remove AuthzMiddleware from the app so tests can run without tokens."""
    app.user_middleware = [m for m in app.user_middleware if m.cls is not AuthzMiddleware]
    app.middleware_stack = app.build_middleware_stack()


@pytest.fixture
def make_client() -> Callable[[dict[type, object]], TestClient]:
    _strip_authz_middleware()
    fake_auth = FakeAuth(role="editor")

    def _make_client(overrides: dict[type, object]) -> TestClient:
        container = FakeContainer(overrides)
        app.dependency_overrides[get_container] = lambda: container
        app.dependency_overrides[get_auth] = lambda: fake_auth
        return TestClient(app)

    yield _make_client
    app.dependency_overrides.clear()


class TestArtifactRoutes:
    def test_create_artifact_success(self, make_client) -> None:
        artifact_id = uuid4()
        response_dto = ArtifactResponse(
            artifact_id=artifact_id,
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )
        create_use_case = FakeUseCase(Success(response_dto))

        client = make_client({CreateArtifactUseCase: create_use_case})

        request = CreateArtifactRequest(
            source_uri="https://example.com/paper.pdf",
            source_filename="paper.pdf",
            artifact_type=ArtifactType.RESEARCH_ARTICLE,
            mime_type=MimeType.PDF,
            storage_location="/storage/paper.pdf",
        )
        response = client.post("/artifacts/", json=request.model_dump())

        assert response.status_code == 201
        data = response.json()
        assert data["artifact_id"] == str(artifact_id)
        assert data["source_filename"] == "paper.pdf"

    def test_get_artifact_not_found(self, make_client) -> None:
        read_model = FakeArtifactReadModel({})
        client = make_client({ArtifactReadModel: read_model})

        response = client.get(f"/artifacts/{uuid4()}")

        assert response.status_code == 404

    def test_list_artifacts(self, make_client) -> None:
        artifact_id = uuid4()
        read_model = FakeArtifactReadModel(
            {
                artifact_id: ArtifactResponse(
                    artifact_id=artifact_id,
                    source_uri="https://example.com/paper.pdf",
                    source_filename="paper.pdf",
                    artifact_type=ArtifactType.RESEARCH_ARTICLE,
                    mime_type=MimeType.PDF,
                    storage_location="/storage/paper.pdf",
                ),
            },
        )
        client = make_client({ArtifactReadModel: read_model})

        response = client.get("/artifacts?skip=0&limit=10")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["artifact_id"] == str(artifact_id)

    def test_update_title_mention_validation_error(self, make_client) -> None:
        artifact_id = uuid4()
        read_model = FakeArtifactReadModel(
            {
                artifact_id: ArtifactResponse(
                    artifact_id=artifact_id,
                    source_uri="https://example.com/paper.pdf",
                    source_filename="paper.pdf",
                    artifact_type=ArtifactType.RESEARCH_ARTICLE,
                    mime_type=MimeType.PDF,
                    storage_location="/storage/paper.pdf",
                ),
            },
        )
        error_result = Failure(AppError("validation", "bad payload"))
        use_case = FakeUseCase(error_result)
        client = make_client({
            UpdateTitleMentionUseCase: use_case,
            ArtifactReadModel: read_model,
        })

        response = client.patch(
            f"/artifacts/{artifact_id}/title_mention",
            json={"title": "Title", "confidence": 0.9},
        )

        assert response.status_code == 400


class TestPageRoutes:
    def test_create_page_success(self, make_client) -> None:
        page_id = uuid4()
        artifact_id = uuid4()
        response_dto = PageResponse(
            page_id=page_id,
            artifact_id=artifact_id,
            name="Intro",
            index=0,
            compound_mentions=[],
            tag_mentions=[],
        )
        create_use_case = FakeUseCase(Success(response_dto))

        client = make_client({CreatePageUseCase: create_use_case})

        request = CreatePageRequest(artifact_id=artifact_id, name="Intro", index=0)
        response = client.post("/pages/", json=request.model_dump(mode="json"))

        assert response.status_code == 201
        data = response.json()
        assert data["page_id"] == str(page_id)
        assert data["name"] == "Intro"

    def test_update_compound_mentions_path_mismatch(self, make_client) -> None:
        path_page_id = uuid4()
        body_page_id = uuid4()
        artifact_id = uuid4()
        read_model = FakePageReadModel(
            {
                path_page_id: PageResponse(
                    page_id=path_page_id,
                    artifact_id=artifact_id,
                    name="Page",
                    index=0,
                    compound_mentions=[],
                    tag_mentions=[],
                ),
            },
        )
        client = make_client({PageReadModel: read_model})
        request = AddCompoundMentionsRequest(
            page_id=body_page_id,
            compound_mentions=[],
        )
        response = client.post(
            f"/pages/{path_page_id}/compound_mentions",
            json=request.model_dump(mode="json"),
        )

        assert response.status_code == 400

    def test_get_page_not_found(self, make_client) -> None:
        read_model = FakePageReadModel({})
        client = make_client({PageReadModel: read_model})

        response = client.get(f"/pages/{uuid4()}")

        assert response.status_code == 404

    def test_delete_page_success(self, make_client) -> None:
        page_id = uuid4()
        artifact_id = uuid4()
        read_model = FakePageReadModel(
            {
                page_id: PageResponse(
                    page_id=page_id,
                    artifact_id=artifact_id,
                    name="Page",
                    index=0,
                    compound_mentions=[],
                    tag_mentions=[],
                ),
            },
        )
        use_case = FakeUseCase(Success(None))
        client = make_client({
            DeletePageUseCase: use_case,
            PageReadModel: read_model,
        })

        response = client.delete(f"/pages/{page_id}")

        assert response.status_code == 204
