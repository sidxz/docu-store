"""GET /stats/member-usage — admin-gated per-member token usage."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from application.dtos.usage_dtos import KindUsage, MemberTokenUsage
from application.ports.token_usage_store import TokenUsageStore
from interfaces.api.main import app
from interfaces.dependencies import get_auth, get_container
from tests.conftest import strip_authz_middleware
from tests.fakes.fake_auth import FakeAuth


class FakeContainer:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]


class FakeUsageStore:
    def __init__(self) -> None:
        self.last_since: datetime | None = None

    async def usage_by_member(self, workspace_id, *, since: datetime):
        self.last_since = since
        return [
            MemberTokenUsage(
                user_id="u1",
                chat=KindUsage(prompt=10, completion=2, total=12, event_count=1),
                ingestion=KindUsage(prompt=100, completion=0, total=100, event_count=3),
                total_tokens=112,
            ),
        ]


def _client(*, is_admin: bool, store: FakeUsageStore | None = None) -> TestClient:
    strip_authz_middleware(app)
    app.dependency_overrides[get_container] = lambda: FakeContainer(
        {TokenUsageStore: store or FakeUsageStore()},
    )
    app.dependency_overrides[get_auth] = lambda: FakeAuth(
        role="admin" if is_admin else "viewer", user_id=uuid4(), workspace_id=uuid4(),
    )
    return TestClient(app)


def test_member_usage_requires_admin() -> None:
    try:
        resp = _client(is_admin=False).get("/stats/member-usage")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_member_usage_returns_split_per_member() -> None:
    try:
        resp = _client(is_admin=True).get("/stats/member-usage?period=month")
        assert resp.status_code == 200
        body = resp.json()
        assert body["period_days"] == 30
        assert body["members"][0]["user_id"] == "u1"
        assert body["members"][0]["chat"]["total"] == 12
        assert body["members"][0]["ingestion"]["total"] == 100
    finally:
        app.dependency_overrides.clear()


def test_member_usage_calendar_month_windows_from_month_start() -> None:
    from application.use_cases.token_limit_use_cases import utc_month_start

    store = FakeUsageStore()
    try:
        resp = _client(is_admin=True, store=store).get(
            "/stats/member-usage?period=calendar_month",
        )
        assert resp.status_code == 200
        assert store.last_since == utc_month_start()
    finally:
        app.dependency_overrides.clear()
