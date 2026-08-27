"""GET /artifacts/processing — must not be shadowed by /artifacts/{artifact_id}."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from application.dtos.workflow_dtos import ProcessingArtifactResponse
from application.use_cases.processing_artifacts_use_case import ListProcessingArtifactsUseCase
from infrastructure.config import Settings
from interfaces.api.main import app
from interfaces.dependencies import get_auth, get_container
from tests.conftest import strip_authz_middleware
from tests.fakes.fake_auth import FakeAuth


class FakeUseCase:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def execute(self, **kw):  # noqa: ANN003
        self.calls.append(kw)
        return [
            ProcessingArtifactResponse(
                artifact_id="a", source_filename="d.pdf", total=4, completed=1, running=2,
                failed=0, percent=25, stage="extracting", active=True, last_activity_at=None,
            ),
        ]


class FakeContainer:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def __getitem__(self, key):  # noqa: ANN001
        return self._mapping[key]


def test_processing_route_returns_rows_for_the_caller() -> None:
    uc, auth = FakeUseCase(), FakeAuth(role="viewer")
    strip_authz_middleware(app)
    app.dependency_overrides[get_container] = lambda: FakeContainer(
        {ListProcessingArtifactsUseCase: uc, Settings: SimpleNamespace(user_llm_keys_enabled=False)},
    )
    app.dependency_overrides[get_auth] = lambda: auth
    try:
        resp = TestClient(app).get("/artifacts/processing")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body[0]["stage"] == "extracting" and body[0]["percent"] == 25
        assert uc.calls[0]["workspace_id"] == auth.workspace_id
        assert uc.calls[0]["user_id"] == auth.user_id
    finally:
        app.dependency_overrides.clear()
