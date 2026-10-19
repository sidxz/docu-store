"""GET/PUT /workspace/embedding — self-serve per-workspace embedding model."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from application.dtos.health_dtos import BulkWorkflowResponse
from application.ports.embedding_generator import EmbeddingGenerator
from application.ports.repositories.artifact_read_models import ArtifactReadModel
from application.ports.user_llm_config import UserLLMConfig
from application.ports.workspace_embedding_config import (
    WorkspaceEmbeddingConfig,
    WorkspaceEmbeddingConfigStore,
)
from application.services.llm_scope import UserLLMScope
from application.workflow_use_cases.trigger_bulk_reembed_use_case import TriggerBulkReEmbedUseCase
from application.workflow_use_cases.workspace_reembed_use_case import (
    ReEmbedProgress,
    WorkspaceReEmbedUseCase,
)
from infrastructure.config import Settings
from interfaces.api.main import app
from interfaces.dependencies import get_auth, get_container
from tests.conftest import strip_authz_middleware
from tests.fakes.fake_auth import FakeAuth

MODEL = "openai/text-embedding-3-small"


class EmbeddingStore:
    def __init__(self) -> None:
        self.by_workspace: dict = {}
        self.workspace_id = None  # the caller's; ``model`` reads and writes it

    @property
    def model(self) -> str | None:
        return self.by_workspace.get(self.workspace_id)

    @model.setter
    def model(self, value: str | None) -> None:
        self.by_workspace[self.workspace_id] = value

    async def get(self, workspace_id):
        model = self.by_workspace.get(workspace_id)
        return WorkspaceEmbeddingConfig(model=model) if model else None

    async def set(self, workspace_id, model, *, updated_by):
        self.by_workspace[workspace_id] = model


class LLMStore:
    def __init__(self, keys: dict[str, str]) -> None:
        self.keys = keys

    async def get_entry(self, workspace_id):
        return None

    async def get_config(self, workspace_id, provider):
        key = self.keys.get(provider)
        return UserLLMConfig(provider="openai", api_key=key) if key else None


class ReadModel:
    def __init__(self, docs: int) -> None:
        self.docs = docs

    async def list_artifacts(self, workspace_id=None, limit=100, **_):
        return [object()] * min(self.docs, limit)


class BulkReEmbed:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.workspaces: list = []

    async def execute(self, workspace_id, targets=None):
        self.calls.append(targets)
        self.workspaces.append(workspace_id)
        return BulkWorkflowResponse(triggered=4, workflow_ids=[], targets=targets)


class ReEmbed:
    def __init__(self) -> None:
        self.state = "done"
        self.error: str | None = None
        self.models: list[str] = []
        self.workspaces: list = []

    async def progress(self, workspace_id, model_name):
        self.models.append(model_name)
        self.workspaces.append(workspace_id)
        return ReEmbedProgress(state=self.state, total=10, done=4, error=self.error)

    async def resume(self, workspace_id, model_name):
        self.models.append(model_name)
        self.workspaces.append(workspace_id)
        return 3


class Generator:
    async def get_model_info(self):
        return {"model_name": "ibm-granite/granite-embedding-english-r2"}


class FakeContainer(dict):
    pass


def _client(*, enabled=True, docs=0, keys=None, role="admin"):
    store, bulk, reembed = EmbeddingStore(), BulkReEmbed(), ReEmbed()
    store.workspace_id = workspace_id = uuid4()
    container = FakeContainer({
        Settings: SimpleNamespace(user_llm_keys_enabled=enabled),
        WorkspaceEmbeddingConfigStore: store,
        UserLLMScope: UserLLMScope(LLMStore(keys or {}), enabled=True, embedding_store=store),
        ArtifactReadModel: ReadModel(docs),
        TriggerBulkReEmbedUseCase: bulk,
        WorkspaceReEmbedUseCase: reembed,
        EmbeddingGenerator: Generator(),
    })
    strip_authz_middleware(app)
    app.dependency_overrides[get_container] = lambda: container
    app.dependency_overrides[get_auth] = lambda: FakeAuth(
        role=role, user_id=uuid4(), workspace_id=workspace_id
    )
    client = TestClient(app)
    client.reembed, client.workspace_id = reembed, workspace_id
    return client, store, bulk


def _put(client, **body):
    return client.put("/workspace/embedding", json=body)


def test_get_reports_local_when_flag_off() -> None:
    try:
        client, _, _ = _client(enabled=False)
        body = client.get("/workspace/embedding").json()
        assert body["enabled"] is False
        assert body["model"] == "local"
        assert body["usable"] is True
        assert body["server_model"] == "ibm-granite/granite-embedding-english-r2"
    finally:
        app.dependency_overrides.clear()


def test_get_flags_a_member_without_a_compatible_key() -> None:
    try:
        client, store, _ = _client(keys={"gemini": "g"})
        store.model = MODEL
        body = client.get("/workspace/embedding").json()
        assert body["model"] == MODEL
        assert body["usable"] is False
        assert "OpenAI or OpenRouter" in body["detail"]
    finally:
        app.dependency_overrides.clear()


def test_put_requires_admin_and_a_known_model() -> None:
    try:
        client, _, _ = _client(role="editor", keys={"openai": "k"})
        assert _put(client, model=MODEL).status_code == 403
        client, _, _ = _client(keys={"openai": "k"})
        assert _put(client, model="acme/unknown").status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_put_without_a_key_for_the_model_is_428_and_saves_nothing() -> None:
    try:
        client, store, _ = _client(keys={"gemini": "g"})
        assert _put(client, model=MODEL).status_code == 428
        assert store.model is None
    finally:
        app.dependency_overrides.clear()


def test_put_with_documents_needs_confirmation_then_reembeds() -> None:
    try:
        client, store, bulk = _client(docs=3, keys={"openrouter": "or"})
        assert _put(client, model=MODEL).status_code == 409
        assert store.model is None
        resp = _put(client, model=MODEL, reembed=True)
        assert resp.status_code == 200
        assert resp.json() == {"model": MODEL, "reembed_workflows": 4}
        assert store.model == MODEL
        assert bulk.calls == [["text", "summaries"]]
    finally:
        app.dependency_overrides.clear()


def test_put_empty_workspace_saves_without_reembed_and_same_model_is_noop() -> None:
    try:
        client, store, bulk = _client(keys={"openai": "k"})
        assert _put(client, model=MODEL).json() == {"model": MODEL, "reembed_workflows": 0}
        assert store.model == MODEL
        assert _put(client, model=MODEL).json()["reembed_workflows"] == 0
        assert bulk.calls == []
    finally:
        app.dependency_overrides.clear()


def test_put_is_refused_when_flag_off() -> None:
    try:
        client, _, _ = _client(enabled=False, keys={"openai": "k"})
        assert _put(client, model=MODEL).status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_get_reports_reembed_progress_against_the_vectors_model_name() -> None:
    try:
        client, store, _ = _client(keys={"openai": "k"})
        client.reembed.state = "running"
        body = client.get("/workspace/embedding").json()
        assert body["reembed"] == {"state": "running", "total": 10, "done": 4, "error": None}
        store.model = MODEL
        client.get("/workspace/embedding")
        # "local" is checked against the server model's name, an API model by its id
        assert client.reembed.models == ["ibm-granite/granite-embedding-english-r2", MODEL]
        client, _, _ = _client(enabled=False)
        assert client.get("/workspace/embedding").json()["reembed"] is None
    finally:
        app.dependency_overrides.clear()


def test_put_is_refused_while_a_reembed_runs() -> None:
    try:
        client, store, bulk = _client(docs=3, keys={"openai": "k"})
        client.reembed.state = "running"
        assert _put(client, model=MODEL, reembed=True).status_code == 409
        assert store.model is None
        assert bulk.calls == []
    finally:
        app.dependency_overrides.clear()


def test_put_is_refused_when_temporal_cannot_say_whether_a_reembed_runs() -> None:
    try:
        client, store, bulk = _client(docs=3, keys={"openai": "k"})
        client.reembed.state = "unknown"
        assert _put(client, model=MODEL, reembed=True).status_code == 409
        assert store.model is None
        assert bulk.calls == []
    finally:
        app.dependency_overrides.clear()


def test_only_admins_see_why_a_reembed_failed() -> None:
    """The provider's error text can quote the workspace's key."""
    try:
        for role, error in (("admin", "Incorrect API key provided: sk-...abcd"), ("editor", None)):
            client, _, _ = _client(role=role)
            client.reembed.state, client.reembed.error = "failed", "Incorrect API key provided: sk-...abcd"
            assert client.get("/workspace/embedding").json()["reembed"]["error"] == error
    finally:
        app.dependency_overrides.clear()


def test_every_route_acts_on_the_callers_workspace() -> None:
    try:
        client, store, bulk = _client(docs=3, keys={"openai": "k"})
        assert _put(client, model=MODEL, reembed=True).status_code == 200
        client.get("/workspace/embedding")
        client.post("/workspace/embedding/reembed")
        ws = client.workspace_id
        assert store.by_workspace == {ws: MODEL}
        assert bulk.workspaces == [ws]
        assert set(client.reembed.workspaces) == {ws}
    finally:
        app.dependency_overrides.clear()


def test_resume_is_admin_only_and_self_serve_only() -> None:
    try:
        client, _, _ = _client(role="editor")
        assert client.post("/workspace/embedding/reembed").status_code == 403
        client, _, _ = _client(enabled=False)
        assert client.post("/workspace/embedding/reembed").status_code == 404
        client, _, _ = _client()
        resp = client.post("/workspace/embedding/reembed")
        assert resp.json() == {"model": "local", "reembed_workflows": 3}
    finally:
        app.dependency_overrides.clear()
