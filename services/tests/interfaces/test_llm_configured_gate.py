"""428 BYO-key gate on chat send + artifact upload/create."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from returns.result import Success

from application.dtos.artifact_dtos import CreateArtifactRequest
from application.dtos.chat_dtos import AgentEvent
from application.ports.user_llm_config import (
    NullUserLLMConfigStore,
    UserLLMConfigStore,
    UserLLMProviderEntry,
)
from application.services.llm_scope import UserLLMScope
from application.use_cases.chat_use_cases import SendMessageUseCase
from application.use_cases.token_limit_use_cases import CheckTokenQuotaUseCase
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from infrastructure.chat.run_registry import ChatRunRegistry
from infrastructure.config import Settings
from interfaces.api.main import app
from interfaces.api.routes.helpers import LLM_NOT_CONFIGURED_DETAIL
from interfaces.dependencies import get_auth, get_container
from tests.conftest import strip_authz_middleware
from tests.fakes.fake_auth import FakeAuth

ENTRY = UserLLMProviderEntry(provider="openai", model="gpt-5-mini", chat_model="gpt-5", key_last4="1234")


class FakeStore:
    def __init__(self, entry: UserLLMProviderEntry | None = None) -> None:
        self.entry = entry
        self.calls = 0

    async def get_entry(self, workspace_id, user_id):
        self.calls += 1
        return self.entry


class FakeQuota:
    async def execute(self, workspace_id, user_id):
        return Success(None)


class FakeSendUseCase:
    async def execute(self, **kwargs):
        yield AgentEvent(type="done")


class FakeContainer:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]


def _settings(*, enabled: bool = True, provider: str = "openai", key: str | None = None):
    return SimpleNamespace(
        user_llm_keys_enabled=enabled,
        self_serve_enabled=False,
        llm_provider=provider,
        openai_api_key=key,
        anthropic_api_key=None,
        google_api_key=None,
        llm_api_key=None,
    )


def _client(store: FakeStore, settings) -> TestClient:
    strip_authz_middleware(app)
    app.dependency_overrides[get_container] = lambda: FakeContainer(
        {
            Settings: settings,
            UserLLMConfigStore: store,
            CheckTokenQuotaUseCase: FakeQuota(),
            SendMessageUseCase: FakeSendUseCase(),
            ChatRunRegistry: ChatRunRegistry(),
            UserLLMScope: UserLLMScope(NullUserLLMConfigStore(), enabled=False),
        },
    )
    app.dependency_overrides[get_auth] = lambda: FakeAuth(
        role="editor", user_id=uuid4(), workspace_id=uuid4(),
    )
    return TestClient(app)


def _send(client: TestClient):
    return client.post(f"/chat/{uuid4()}/messages", json={"message": "hi"})


def test_chat_send_428_without_provider() -> None:
    store = FakeStore()
    try:
        resp = _send(_client(store, _settings()))
        assert resp.status_code == 428
        assert resp.json()["detail"] == LLM_NOT_CONFIGURED_DETAIL
        assert store.calls == 1
    finally:
        app.dependency_overrides.clear()


def test_chat_send_passes_with_provider() -> None:
    store = FakeStore(ENTRY)
    try:
        assert _send(_client(store, _settings())).status_code == 200
        assert store.calls == 1
    finally:
        app.dependency_overrides.clear()


def test_flag_off_never_touches_store() -> None:
    store = FakeStore()
    try:
        assert _send(_client(store, _settings(enabled=False))).status_code == 200
        assert store.calls == 0
    finally:
        app.dependency_overrides.clear()


def test_server_key_or_local_provider_skips_store() -> None:
    for settings in (_settings(key="sk-server"), _settings(provider="ollama")):
        store = FakeStore()
        try:
            assert _send(_client(store, settings)).status_code == 200
            assert store.calls == 0
        finally:
            app.dependency_overrides.clear()


def test_upload_428_before_saga_runs() -> None:
    # No ArtifactUploadSaga in the container: reaching it would KeyError → 500.
    try:
        resp = _client(FakeStore(), _settings()).post(
            "/artifacts/upload",
            files={"file": ("paper.pdf", b"%PDF", "application/pdf")},
            data={"artifact_type": "RESEARCH_ARTICLE"},
        )
        assert resp.status_code == 428
        assert resp.json()["detail"] == LLM_NOT_CONFIGURED_DETAIL
    finally:
        app.dependency_overrides.clear()


def test_create_428_before_use_case_runs() -> None:
    body = CreateArtifactRequest(
        source_uri="https://example.com/paper.pdf",
        source_filename="paper.pdf",
        artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF,
        storage_location="/storage/paper.pdf",
    )
    try:
        resp = _client(FakeStore(), _settings()).post("/artifacts/", json=body.model_dump())
        assert resp.status_code == 428
    finally:
        app.dependency_overrides.clear()
