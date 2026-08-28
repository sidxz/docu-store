"""429 quota enforcement on chat send + artifact upload/create."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from returns.result import Failure, Success

from application.dtos.chat_dtos import AgentEvent
from application.dtos.errors import AppError
from application.ports.user_llm_config import NullUserLLMConfigStore
from application.services.llm_scope import UserLLMScope
from application.use_cases.chat_use_cases import SendMessageUseCase
from application.use_cases.token_limit_use_cases import CheckTokenQuotaUseCase
from infrastructure.chat.run_registry import ChatRunRegistry
from infrastructure.config import Settings
from interfaces.api.main import app
from interfaces.dependencies import get_auth, get_container
from tests.conftest import strip_authz_middleware
from tests.fakes.fake_auth import FakeAuth

DETAIL = "Monthly token limit reached: 150 of 100 tokens used. Resets on the 1st (UTC)."
OVER_LIMIT = Failure(AppError("rate_limited", DETAIL))


class FakeQuota:
    def __init__(self, result) -> None:
        self._result = result
        self.calls = 0

    async def execute(self, workspace_id, user_id):
        self.calls += 1
        return self._result


class FakeSendUseCase:
    async def execute(self, **kwargs):
        yield AgentEvent(type="done")


class FakeContainer:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]


def _client(*, quota: FakeQuota, role: str = "editor") -> TestClient:
    strip_authz_middleware(app)
    app.dependency_overrides[get_container] = lambda: FakeContainer(
        {
            Settings: SimpleNamespace(user_llm_keys_enabled=False, self_serve_enabled=False),
            CheckTokenQuotaUseCase: quota,
            SendMessageUseCase: FakeSendUseCase(),
            ChatRunRegistry: ChatRunRegistry(),
            UserLLMScope: UserLLMScope(NullUserLLMConfigStore(), enabled=False),
        },
    )
    app.dependency_overrides[get_auth] = lambda: FakeAuth(
        role=role, user_id=uuid4(), workspace_id=uuid4(),
    )
    return TestClient(app)


def test_chat_send_blocked_over_limit() -> None:
    quota = FakeQuota(OVER_LIMIT)
    try:
        resp = _client(quota=quota).post(
            f"/chat/{uuid4()}/messages", json={"message": "hi"},
        )
        assert resp.status_code == 429
        assert resp.json()["detail"] == DETAIL
        assert quota.calls == 1
    finally:
        app.dependency_overrides.clear()


def test_chat_send_passes_under_limit() -> None:
    quota = FakeQuota(Success(None))
    try:
        resp = _client(quota=quota).post(
            f"/chat/{uuid4()}/messages", json={"message": "hi"},
        )
        assert resp.status_code == 200
        assert quota.calls == 1
    finally:
        app.dependency_overrides.clear()


def test_chat_send_admin_exempt() -> None:
    quota = FakeQuota(OVER_LIMIT)
    try:
        resp = _client(quota=quota, role="admin").post(
            f"/chat/{uuid4()}/messages", json={"message": "hi"},
        )
        assert resp.status_code == 200
        assert quota.calls == 0  # gate short-circuits before the use case
    finally:
        app.dependency_overrides.clear()


def test_upload_blocked_over_limit() -> None:
    quota = FakeQuota(OVER_LIMIT)
    try:
        resp = _client(quota=quota).post(
            "/artifacts/upload",
            files={"file": ("t.pdf", b"x", "application/pdf")},
            data={"artifact_type": "UNCLASSIFIED"},
        )
        assert resp.status_code == 429
        assert resp.json()["detail"] == DETAIL
    finally:
        app.dependency_overrides.clear()


def test_create_artifact_blocked_over_limit() -> None:
    quota = FakeQuota(OVER_LIMIT)
    try:
        resp = _client(quota=quota).post(
            "/artifacts/",
            json={
                "artifact_type": "UNCLASSIFIED",
                "mime_type": "application/pdf",
                "storage_location": "blob://test",
            },
        )
        assert resp.status_code == 429
    finally:
        app.dependency_overrides.clear()


def test_create_page_blocked_over_limit() -> None:
    """LLM enrichment cascades off page creation — it must be gated too."""
    quota = FakeQuota(OVER_LIMIT)
    try:
        resp = _client(quota=quota).post(
            "/pages/",
            json={"artifact_id": str(uuid4()), "name": "p1", "index": 0},
        )
        assert resp.status_code == 429
        assert resp.json()["detail"] == DETAIL
    finally:
        app.dependency_overrides.clear()
