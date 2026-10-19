"""Settings → Stats shows only the caller's workspace (Temporal and Qdrant are shared)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from interfaces.api.main import app
from interfaces.api.routes import stats_routes
from interfaces.dependencies import get_auth, get_container
from tests.conftest import strip_authz_middleware
from tests.fakes.fake_auth import FakeAuth

OURS, THEIRS = str(uuid4()), str(uuid4())
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _wf(workflow_id: str):
    return SimpleNamespace(
        id=workflow_id, workflow_type="EmbeddingWorkflow", start_time=T0, close_time=T0 + timedelta(seconds=2)
    )


class FakeTemporal:
    async def list_workflows(self, query):
        if "Completed" in query or "Failed" in query:
            for wf in (_wf(f"embedding-{OURS}"), _wf(f"embedding-{THEIRS}")):
                yield wf

    def get_workflow_handle(self, workflow_id):
        return SimpleNamespace(describe=self._describe)

    async def _describe(self):
        return SimpleNamespace()


def test_workflow_stats_leave_out_other_workspaces(monkeypatch) -> None:
    async def connect(_address):
        return FakeTemporal()

    async def entity_ids(_container, _workspace_id):
        return {OURS}

    monkeypatch.setattr(stats_routes.Client, "connect", connect)
    monkeypatch.setattr(stats_routes, "_workspace_entity_ids", entity_ids)
    strip_authz_middleware(app)
    app.dependency_overrides[get_container] = lambda: {}
    app.dependency_overrides[get_auth] = lambda: FakeAuth(role="admin", user_id=uuid4(), workspace_id=uuid4())
    try:
        body = TestClient(app).get("/stats/workflows").json()
        assert [c["count"] for c in body["completed"]] == [1]
        assert [f["workflow_id"] for f in body["recent_failures"]] == [f"embedding-{OURS}"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
async def test_workspace_entity_ids_are_read_from_that_workspace_only(monkeypatch) -> None:
    """The real Mongo query behind the filter above (local docker-compose / CI mongodb)."""
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient("mongodb://localhost:27017", serverSelectionTimeoutMS=3000)
    try:
        await client.admin.command("ping")
    except Exception as exc:  # pragma: no cover - only hit with no local/CI Mongo
        pytest.skip(f"no Mongo reachable at localhost:27017: {exc}")
    db_name = f"docu_store_test_{uuid4().hex[:8]}"
    monkeypatch.setattr(
        stats_routes,
        "settings",
        SimpleNamespace(mongo_db=db_name, mongo_artifacts_collection="a", mongo_pages_collection="p"),
    )
    ours, theirs = uuid4(), uuid4()
    db = client[db_name]
    try:
        await db["a"].insert_many([
            {"artifact_id": "art-ours", "workspace_id": str(ours)},
            {"artifact_id": "art-theirs", "workspace_id": str(theirs)},
        ])
        await db["p"].insert_many([
            {"page_id": "page-ours", "workspace_id": str(ours)},
            {"page_id": "page-theirs", "workspace_id": str(theirs)},
        ])
        ids = await stats_routes._workspace_entity_ids({AsyncIOMotorClient: client}, ours)
        assert ids == {"art-ours", "page-ours"}
    finally:
        await client.drop_database(db_name)
        client.close()
