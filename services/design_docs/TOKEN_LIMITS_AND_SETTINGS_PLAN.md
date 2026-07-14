# Token Limits & Settings Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admin-configurable monthly token limits per user (with a workspace default) enforced via 429 pre-flight on chat/upload, plus a settings-page revamp into sub-route tabs where Token Settings, Stats, and Status are admin-only.

**Architecture:** New `token_limits` Mongo collection behind a `TokenLimitStore` port (rows keyed `(workspace_id, user_id)`, `user_id=null` = workspace default, `limit=null` = unlimited). A `CheckTokenQuotaUseCase` resolves override→default→unlimited and compares against the existing ledger's `sum_for_user` since UTC month start. Frontend: `app/[workspace]/settings/` becomes a layout with a vertical link rail and nested routes; Stats/Status page bodies move under it; old routes redirect.

**Tech Stack:** FastAPI + Motor + `returns.result` + Lagom DI + pytest (backend); Next.js 16 App Router + TanStack Query v5 + `authFetchJson` manual types (frontend).

**Spec:** `services/design_docs/TOKEN_LIMITS_AND_SETTINGS.md` (approved).

## Global Constraints

- Branch: `token-limits` (stacked on `token-usage-ledger`). All work commits here.
- Run all Python via `uv run` from `services/` (e.g. `uv run pytest tests/... -v`).
- Frontend checks from `web/`: `pnpm --filter portal lint` (tsc --noEmit) and `pnpm --filter portal build`.
- Limit semantics (exact): calendar month, **UTC**; `limit=None` = unlimited; `limit=0` = fully blocked; block when `used >= limit`; admins (`auth.is_admin`) always exempt; quota check **fails open** on infrastructure errors.
- 429 detail string (exact format): `"Monthly token limit reached: {used:,} of {limit:,} tokens used. Resets on the 1st (UTC)."`
- Use cases return `returns.result` `Success`/`Failure(AppError(...))` — never raise for domain outcomes.
- Admin route guard (exact, matches `/stats/*`): `if not auth.is_admin: raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")`.
- Tests: no real Mongo, no mongomock — pure module-helper tests + hand-rolled fakes + `TestClient` with `FakeAuth`/`FakeContainer` and dependency overrides; always `app.dependency_overrides.clear()` in `finally`.
- No OpenAPI regen; frontend uses `authFetchJson`/`authFetch` with hand-written interfaces.
- Frontend color rule: green `emerald-500`, warn `amber-500` (≥80%), over `red-500` (≥100%). Do not use `ds-danger` (doesn't exist).

---

### Task 1: TokenLimitStore port + Mongo adapter + wiring

**Files:**
- Modify: `services/application/dtos/usage_dtos.py` (append `TokenLimitEntry`)
- Create: `services/application/ports/token_limit_store.py`
- Create: `services/infrastructure/read_repositories/mongo_token_limit_store.py`
- Modify: `services/infrastructure/config.py:80-83` (add collection field after `mongo_token_usage_collection`)
- Modify: `services/infrastructure/di/container.py:853-860` (register store after `TokenUsageStore` block)
- Modify: `services/interfaces/api/main.py:93-98` (ensure indexes after token-usage block)
- Test: `services/tests/infrastructure/test_token_limit_store.py`

**Interfaces:**
- Consumes: nothing new (mirrors `MongoTokenUsageStore`).
- Produces (later tasks rely on these exact names):
  - `TokenLimitEntry(BaseModel)` with `user_id: UUID | None`, `limit: int | None` (in `application/dtos/usage_dtos.py`)
  - `TokenLimitStore` Protocol: `get(workspace_id: UUID, user_id: UUID | None) -> TokenLimitEntry | None`, `list_for_workspace(workspace_id: UUID) -> list[TokenLimitEntry]`, `set(workspace_id: UUID, user_id: UUID | None, limit: int | None, updated_by: UUID) -> None`, `delete(workspace_id: UUID, user_id: UUID) -> None`, `ensure_indexes() -> None` (all async)
  - DI key `container[TokenLimitStore]`; settings field `settings.mongo_token_limits_collection`

- [ ] **Step 1: Write the failing test**

Create `services/tests/infrastructure/test_token_limit_store.py`:

```python
"""Pure-logic tests for MongoTokenLimitStore doc mapping (no DB)."""

from __future__ import annotations

from uuid import uuid4

from application.dtos.usage_dtos import TokenLimitEntry
from infrastructure.read_repositories.mongo_token_limit_store import (
    _doc_to_entry,
    _entry_doc,
)


def test_entry_doc_for_user_override() -> None:
    ws, user, admin = uuid4(), uuid4(), uuid4()
    doc = _entry_doc(ws, user, 500_000, admin)
    assert doc["workspace_id"] == str(ws)
    assert doc["user_id"] == str(user)
    assert doc["limit"] == 500_000
    assert doc["updated_by"] == str(admin)
    assert doc["updated_at"] is not None


def test_entry_doc_for_workspace_default_and_unlimited() -> None:
    doc = _entry_doc(uuid4(), None, None, uuid4())
    assert doc["user_id"] is None  # default row
    assert doc["limit"] is None  # unlimited


def test_doc_to_entry_round_trip_zero_limit() -> None:
    ws, user, admin = uuid4(), uuid4(), uuid4()
    entry = _doc_to_entry(_entry_doc(ws, user, 0, admin))
    assert entry == TokenLimitEntry(user_id=user, limit=0)


def test_doc_to_entry_default_row() -> None:
    entry = _doc_to_entry({"workspace_id": "w", "user_id": None, "limit": 123})
    assert entry.user_id is None
    assert entry.limit == 123
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services && uv run pytest tests/infrastructure/test_token_limit_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'infrastructure.read_repositories.mongo_token_limit_store'`

- [ ] **Step 3: Add the DTO**

Append to `services/application/dtos/usage_dtos.py`:

```python
class TokenLimitEntry(BaseModel):
    """One token-limit row: a per-user override, or the workspace default when user_id is None.

    ``limit`` semantics: None = unlimited, 0 = fully blocked.
    """

    user_id: UUID | None = None
    limit: int | None = None
```

- [ ] **Step 4: Create the port**

Create `services/application/ports/token_limit_store.py`:

```python
"""Port for admin-configured monthly token limits."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from application.dtos.usage_dtos import TokenLimitEntry


class TokenLimitStore(Protocol):
    """Workspace token limits: per-user override rows plus a workspace-default row.

    Rows are keyed by (workspace_id, user_id); user_id=None is the workspace
    default. Resolution (override ?? default ?? unlimited) lives in the
    application layer, not here — this port is dumb CRUD.
    """

    async def get(self, workspace_id: UUID, user_id: UUID | None) -> TokenLimitEntry | None: ...

    async def list_for_workspace(self, workspace_id: UUID) -> list[TokenLimitEntry]: ...

    async def set(
        self,
        workspace_id: UUID,
        user_id: UUID | None,
        limit: int | None,
        updated_by: UUID,
    ) -> None:
        """Upsert one row. ``user_id=None`` sets the workspace default."""
        ...

    async def delete(self, workspace_id: UUID, user_id: UUID) -> None:
        """Remove a per-user override (the default is cleared by set(None))."""
        ...

    async def ensure_indexes(self) -> None: ...
```

- [ ] **Step 5: Create the adapter**

Create `services/infrastructure/read_repositories/mongo_token_limit_store.py`:

```python
"""MongoDB adapter for the TokenLimitStore port."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from motor.motor_asyncio import AsyncIOMotorClient

from application.dtos.usage_dtos import TokenLimitEntry

log = structlog.get_logger(__name__)


def _entry_doc(
    workspace_id: UUID,
    user_id: UUID | None,
    limit: int | None,
    updated_by: UUID,
) -> dict:
    return {
        "workspace_id": str(workspace_id),
        "user_id": str(user_id) if user_id else None,
        "limit": limit,
        "updated_at": datetime.now(UTC),
        "updated_by": str(updated_by),
    }


def _doc_to_entry(doc: dict) -> TokenLimitEntry:
    user_id = doc.get("user_id")
    return TokenLimitEntry(
        user_id=UUID(user_id) if user_id else None,
        limit=doc.get("limit"),
    )


class MongoTokenLimitStore:
    """Workspace token limits: per-user override rows + a workspace-default row."""

    def __init__(
        self,
        client: AsyncIOMotorClient,
        db_name: str,
        collection_name: str = "token_limits",
    ) -> None:
        self._coll = client[db_name][collection_name]

    async def get(self, workspace_id: UUID, user_id: UUID | None) -> TokenLimitEntry | None:
        doc = await self._coll.find_one(
            {"workspace_id": str(workspace_id), "user_id": str(user_id) if user_id else None},
        )
        return _doc_to_entry(doc) if doc else None

    async def list_for_workspace(self, workspace_id: UUID) -> list[TokenLimitEntry]:
        docs = await self._coll.find({"workspace_id": str(workspace_id)}).to_list(length=1000)
        return [_doc_to_entry(d) for d in docs]

    async def set(
        self,
        workspace_id: UUID,
        user_id: UUID | None,
        limit: int | None,
        updated_by: UUID,
    ) -> None:
        query = {"workspace_id": str(workspace_id), "user_id": str(user_id) if user_id else None}
        await self._coll.replace_one(
            query,
            _entry_doc(workspace_id, user_id, limit, updated_by),
            upsert=True,
        )

    async def delete(self, workspace_id: UUID, user_id: UUID) -> None:
        await self._coll.delete_one(
            {"workspace_id": str(workspace_id), "user_id": str(user_id)},
        )

    async def ensure_indexes(self) -> None:
        # Unique also covers the (ws, null) default row — Mongo treats null as a
        # value in unique indexes, so at most one default per workspace.
        await self._coll.create_index(
            [("workspace_id", 1), ("user_id", 1)],
            unique=True,
            name="idx_limits_ws_user",
        )
        log.info("token_limits.indexes_created")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd services && uv run pytest tests/infrastructure/test_token_limit_store.py -v`
Expected: 4 PASS

- [ ] **Step 7: Wire config, DI, startup**

In `services/infrastructure/config.py`, directly after the `mongo_token_usage_collection` field (line 80-83), add:

```python
    mongo_token_limits_collection: str = Field(
        default="token_limits",
        validation_alias="MONGO_TOKEN_LIMITS_COLLECTION",
    )
```

In `services/infrastructure/di/container.py`, directly after the `container[TokenUsageStore] = ...` block (lines 856-860), add:

```python
    from application.ports.token_limit_store import TokenLimitStore
    from infrastructure.read_repositories.mongo_token_limit_store import MongoTokenLimitStore

    container[TokenLimitStore] = lambda c: MongoTokenLimitStore(
        client=c[AsyncIOMotorClient],
        db_name=settings.mongo_db,
        collection_name=settings.mongo_token_limits_collection,
    )
```

In `services/interfaces/api/main.py`, directly after the token-usage `ensure_indexes` block (lines 93-98), add:

```python
            # Ensure token limit indexes
            from application.ports.token_limit_store import TokenLimitStore

            limit_store = container[TokenLimitStore]
            await limit_store.ensure_indexes()
            logger.info("mongodb_token_limits_indexes_initialized")
```

- [ ] **Step 8: Run the broader suite slice**

Run: `cd services && uv run pytest tests/infrastructure tests/application -q`
Expected: all pass (no regressions)

- [ ] **Step 9: Commit**

```bash
git add services/application/dtos/usage_dtos.py services/application/ports/token_limit_store.py services/infrastructure/read_repositories/mongo_token_limit_store.py services/infrastructure/config.py services/infrastructure/di/container.py services/interfaces/api/main.py services/tests/infrastructure/test_token_limit_store.py
git commit -m "feat(usage): TokenLimitStore port + Mongo adapter for workspace token limits"
```

---

### Task 2: CheckTokenQuotaUseCase + limit resolution helpers

**Files:**
- Create: `services/application/use_cases/token_limit_use_cases.py`
- Test: `services/tests/application/test_check_token_quota.py`

**Interfaces:**
- Consumes: `TokenLimitStore` (Task 1), `TokenUsageStore.sum_for_user(ws, user, *, since=None, kind=None) -> TokenUsageDTO` (exists), `AppError(category, message)`.
- Produces (later tasks rely on these exact names, all in `application/use_cases/token_limit_use_cases.py`):
  - `utc_month_start(now: datetime | None = None) -> datetime`
  - `async effective_limit(store: TokenLimitStore, workspace_id: UUID, user_id: UUID) -> int | None`
  - `CheckTokenQuotaUseCase(token_limit_store, token_usage_store)` with `async execute(workspace_id: UUID, user_id: UUID) -> Result[None, AppError]`; over-limit → `Failure(AppError("rate_limited", "<detail string from Global Constraints>"))`
  - New `AppError` category literal: `"rate_limited"`

- [ ] **Step 1: Write the failing test**

Create `services/tests/application/test_check_token_quota.py`:

```python
"""CheckTokenQuotaUseCase — monthly limit resolution + pre-flight gate."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from returns.result import Failure, Success

from application.dtos.chat_dtos import TokenUsageDTO
from application.dtos.usage_dtos import TokenLimitEntry
from application.use_cases.token_limit_use_cases import (
    CheckTokenQuotaUseCase,
    effective_limit,
    utc_month_start,
)

WS, USER = uuid4(), uuid4()


class FakeLimitStore:
    """Rows keyed by user_id (None = workspace default); missing key = no row."""

    def __init__(self, rows: dict | None = None) -> None:
        self._rows = rows or {}

    async def get(self, workspace_id, user_id):
        if user_id in self._rows:
            return TokenLimitEntry(user_id=user_id, limit=self._rows[user_id])
        return None


class FakeUsageStore:
    def __init__(self, total: int = 0, *, raises: bool = False) -> None:
        self._total = total
        self._raises = raises
        self.last_since = None

    async def sum_for_user(self, workspace_id, user_id, *, since=None, kind=None):
        if self._raises:
            raise RuntimeError("mongo down")
        self.last_since = since
        return TokenUsageDTO(prompt=0, completion=0, total=self._total)


def _uc(rows: dict | None, usage: FakeUsageStore) -> CheckTokenQuotaUseCase:
    return CheckTokenQuotaUseCase(
        token_limit_store=FakeLimitStore(rows),
        token_usage_store=usage,
    )


def test_utc_month_start() -> None:
    assert utc_month_start(datetime(2026, 7, 13, 22, 5, tzinfo=UTC)) == datetime(
        2026, 7, 1, tzinfo=UTC,
    )


async def test_no_rows_means_unlimited() -> None:
    result = await _uc(None, FakeUsageStore(total=10**12)).execute(WS, USER)
    assert isinstance(result, Success)


async def test_under_default_limit_passes_and_windows_by_month() -> None:
    usage = FakeUsageStore(total=50)
    result = await _uc({None: 100}, usage).execute(WS, USER)
    assert isinstance(result, Success)
    assert usage.last_since == utc_month_start()


async def test_at_limit_blocks_with_detail_message() -> None:
    result = await _uc({None: 100}, FakeUsageStore(total=100)).execute(WS, USER)
    assert isinstance(result, Failure)
    err = result.failure()
    assert err.category == "rate_limited"
    assert err.message == (
        "Monthly token limit reached: 100 of 100 tokens used. Resets on the 1st (UTC)."
    )


async def test_override_beats_default() -> None:
    result = await _uc({None: 100, USER: 200}, FakeUsageStore(total=150)).execute(WS, USER)
    assert isinstance(result, Success)


async def test_null_override_is_unlimited_over_finite_default() -> None:
    result = await _uc({None: 100, USER: None}, FakeUsageStore(total=10**12)).execute(WS, USER)
    assert isinstance(result, Success)


async def test_zero_limit_blocks_immediately() -> None:
    result = await _uc({USER: 0}, FakeUsageStore(total=0)).execute(WS, USER)
    assert isinstance(result, Failure)


async def test_fails_open_on_infrastructure_error() -> None:
    result = await _uc({None: 100}, FakeUsageStore(raises=True)).execute(WS, USER)
    assert isinstance(result, Success)


async def test_effective_limit_resolution() -> None:
    assert await effective_limit(FakeLimitStore({USER: 5}), WS, USER) == 5
    assert await effective_limit(FakeLimitStore({None: 7}), WS, USER) == 7
    assert await effective_limit(FakeLimitStore({}), WS, USER) is None
    assert await effective_limit(FakeLimitStore({None: 7, USER: None}), WS, USER) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services && uv run pytest tests/application/test_check_token_quota.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'application.use_cases.token_limit_use_cases'`

- [ ] **Step 3: Implement the use case**

Create `services/application/use_cases/token_limit_use_cases.py`:

```python
"""Use cases for admin-configured monthly token limits."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from returns.result import Failure, Result, Success

from application.dtos.errors import AppError
from application.ports.token_limit_store import TokenLimitStore
from application.ports.token_usage_store import TokenUsageStore

log = structlog.get_logger(__name__)


def utc_month_start(now: datetime | None = None) -> datetime:
    """First instant of the current calendar month, UTC — limits reset on the 1st."""
    now = now or datetime.now(UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC)


async def effective_limit(
    store: TokenLimitStore,
    workspace_id: UUID,
    user_id: UUID,
) -> int | None:
    """Resolve a user's monthly token limit: override ?? workspace default ?? unlimited.

    An existing override row with limit=None makes that user explicitly unlimited,
    even over a finite workspace default.
    """
    override = await store.get(workspace_id, user_id)
    if override is not None:
        return override.limit
    default = await store.get(workspace_id, None)
    return default.limit if default is not None else None


class CheckTokenQuotaUseCase:
    """Pre-flight monthly quota gate for chat send and document upload/create.

    Soft ceiling: compares already-recorded ledger usage, so concurrent in-flight
    requests can overshoot slightly. Fails open on infrastructure errors — a
    broken limits/ledger read must not take chat down.
    """

    def __init__(
        self,
        token_limit_store: TokenLimitStore,
        token_usage_store: TokenUsageStore,
    ) -> None:
        self._limits = token_limit_store
        self._usage = token_usage_store

    async def execute(self, workspace_id: UUID, user_id: UUID) -> Result[None, AppError]:
        try:
            limit = await effective_limit(self._limits, workspace_id, user_id)
            if limit is None:
                return Success(None)
            usage = await self._usage.sum_for_user(
                workspace_id, user_id, since=utc_month_start(),
            )
            if usage.total >= limit:
                return Failure(
                    AppError(
                        "rate_limited",
                        f"Monthly token limit reached: {usage.total:,} of {limit:,} "
                        "tokens used. Resets on the 1st (UTC).",
                    ),
                )
            return Success(None)
        except Exception as e:
            log.warning("quota.check_failed", error=str(e), exc_info=True)
            return Success(None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services && uv run pytest tests/application/test_check_token_quota.py -v`
Expected: 9 PASS

- [ ] **Step 5: Commit**

```bash
git add services/application/use_cases/token_limit_use_cases.py services/tests/application/test_check_token_quota.py
git commit -m "feat(usage): CheckTokenQuotaUseCase with month window + override resolution"
```

---

### Task 3: Admin token-limits CRUD endpoints (+ conftest strip-middleware extraction)

**Files:**
- Modify: `services/interfaces/api/routes/workspace_routes.py` (whole file shown below)
- Modify: `services/tests/conftest.py` (append `strip_authz_middleware`)
- Modify: `services/tests/interfaces/test_stats_member_usage.py` (use shared helper)
- Modify: `services/tests/interfaces/test_api_routes.py` (use shared helper)
- Test: `services/tests/interfaces/test_token_limit_routes.py`

**Interfaces:**
- Consumes: `TokenLimitStore` + `TokenLimitEntry` (Task 1).
- Produces:
  - `GET /workspace/token-limits` → `{"default_limit": int|null, "overrides": [{"user_id": "...", "limit": int|null}]}`
  - `PUT /workspace/token-limits/default` body `{"limit": int|null}` → 204
  - `PUT /workspace/token-limits/{user_id}` body `{"limit": int|null}` → 204
  - `DELETE /workspace/token-limits/{user_id}` → 204
  - `tests.conftest.strip_authz_middleware(app)` for all route tests

- [ ] **Step 1: Extract the shared test helper**

Append to `services/tests/conftest.py`:

```python
def strip_authz_middleware(app) -> None:
    """Remove AuthzMiddleware so route tests can run without real tokens.

    Without this, the real middleware 401s every request before
    ``Depends(get_auth)`` runs, so dependency overrides never apply.
    """
    from sentinel_auth.authz_middleware import AuthzMiddleware

    app.user_middleware = [m for m in app.user_middleware if m.cls is not AuthzMiddleware]
    app.middleware_stack = app.build_middleware_stack()
```

In `services/tests/interfaces/test_stats_member_usage.py` and `services/tests/interfaces/test_api_routes.py`: delete each file's local `_strip_authz_middleware` function (and its now-unused `AuthzMiddleware` import), add `from tests.conftest import strip_authz_middleware`, and replace calls `_strip_authz_middleware()` → `strip_authz_middleware(app)`.

Run: `cd services && uv run pytest tests/interfaces -q` — Expected: all pass.

- [ ] **Step 2: Write the failing route test**

Create `services/tests/interfaces/test_token_limit_routes.py`:

```python
"""Admin CRUD for workspace token limits."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from application.dtos.usage_dtos import TokenLimitEntry
from application.ports.token_limit_store import TokenLimitStore
from interfaces.api.main import app
from interfaces.dependencies import get_auth, get_container
from tests.conftest import strip_authz_middleware
from tests.fakes.fake_auth import FakeAuth

USER_A = uuid4()
ADMIN_ID = uuid4()
WS_ID = uuid4()


class FakeLimitStore:
    def __init__(self) -> None:
        self.rows = [
            TokenLimitEntry(user_id=None, limit=1_000_000),
            TokenLimitEntry(user_id=USER_A, limit=None),
        ]
        self.set_calls: list[tuple] = []
        self.delete_calls: list[tuple] = []

    async def list_for_workspace(self, workspace_id):
        return self.rows

    async def set(self, workspace_id, user_id, limit, updated_by):
        self.set_calls.append((workspace_id, user_id, limit, updated_by))

    async def delete(self, workspace_id, user_id):
        self.delete_calls.append((workspace_id, user_id))


class FakeContainer:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]


def _client(store: FakeLimitStore, *, is_admin: bool = True) -> TestClient:
    strip_authz_middleware(app)
    app.dependency_overrides[get_container] = lambda: FakeContainer({TokenLimitStore: store})
    app.dependency_overrides[get_auth] = lambda: FakeAuth(
        role="admin" if is_admin else "viewer", user_id=ADMIN_ID, workspace_id=WS_ID,
    )
    return TestClient(app)


def test_get_limits_requires_admin() -> None:
    try:
        assert _client(FakeLimitStore(), is_admin=False).get("/workspace/token-limits").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_get_limits_splits_default_and_overrides() -> None:
    try:
        resp = _client(FakeLimitStore()).get("/workspace/token-limits")
        assert resp.status_code == 200
        body = resp.json()
        assert body["default_limit"] == 1_000_000
        assert body["overrides"] == [{"user_id": str(USER_A), "limit": None}]
    finally:
        app.dependency_overrides.clear()


def test_put_default_upserts_null_user_row() -> None:
    store = FakeLimitStore()
    try:
        resp = _client(store).put("/workspace/token-limits/default", json={"limit": 5_000_000})
        assert resp.status_code == 204
        assert store.set_calls == [(WS_ID, None, 5_000_000, ADMIN_ID)]
    finally:
        app.dependency_overrides.clear()


def test_put_user_override_and_delete() -> None:
    store = FakeLimitStore()
    try:
        client = _client(store)
        assert client.put(f"/workspace/token-limits/{USER_A}", json={"limit": None}).status_code == 204
        assert store.set_calls == [(WS_ID, USER_A, None, ADMIN_ID)]
        assert client.delete(f"/workspace/token-limits/{USER_A}").status_code == 204
        assert store.delete_calls == [(WS_ID, USER_A)]
    finally:
        app.dependency_overrides.clear()


def test_put_rejects_negative_limit() -> None:
    try:
        resp = _client(FakeLimitStore()).put("/workspace/token-limits/default", json={"limit": -1})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_mutations_require_admin() -> None:
    try:
        client = _client(FakeLimitStore(), is_admin=False)
        assert client.put("/workspace/token-limits/default", json={"limit": 1}).status_code == 403
        assert client.put(f"/workspace/token-limits/{USER_A}", json={"limit": 1}).status_code == 403
        assert client.delete(f"/workspace/token-limits/{USER_A}").status_code == 403
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd services && uv run pytest tests/interfaces/test_token_limit_routes.py -v`
Expected: FAIL — 404s (routes don't exist yet)

- [ ] **Step 4: Implement the routes**

Replace `services/interfaces/api/routes/workspace_routes.py` in full:

```python
"""Workspace routes — Sentinel member/group proxies + admin token-limit config."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from lagom import Container
from pydantic import BaseModel, Field
from sentinel_auth import RequestAuth

from application.dtos.usage_dtos import TokenLimitEntry
from application.ports.token_limit_store import TokenLimitStore
from interfaces.dependencies import get_auth, get_container

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/members", status_code=200)
async def search_members(
    auth: Annotated[RequestAuth, Depends(get_auth)],
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[dict]:
    """Search workspace members by name or email.

    Proxies to Sentinel's workspace member list endpoint.
    """
    return await auth.search_members(query=q, limit=limit)


@router.get("/groups", status_code=200)
async def list_groups(
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> list[dict]:
    """List groups in the current workspace."""
    return await auth.list_groups()


# ── Token limits (admin) ────────────────────────────────────────────────────


class TokenLimitBody(BaseModel):
    limit: int | None = Field(default=None, ge=0)


class WorkspaceTokenLimitsResponse(BaseModel):
    default_limit: int | None
    overrides: list[TokenLimitEntry]


def _require_admin(auth: RequestAuth) -> None:
    if not auth.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


@router.get("/token-limits", status_code=status.HTTP_200_OK)
async def get_token_limits(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> WorkspaceTokenLimitsResponse:
    """Workspace-default + per-user monthly token limits (admin only)."""
    _require_admin(auth)
    rows = await container[TokenLimitStore].list_for_workspace(auth.workspace_id)
    default = next((r for r in rows if r.user_id is None), None)
    return WorkspaceTokenLimitsResponse(
        default_limit=default.limit if default else None,
        overrides=[r for r in rows if r.user_id is not None],
    )


# NOTE: /default must be declared before /{user_id} — otherwise "default"
# matches the UUID path param and 422s instead of reaching this route.
@router.put("/token-limits/default", status_code=status.HTTP_204_NO_CONTENT)
async def set_default_token_limit(
    body: TokenLimitBody,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Set the workspace-default monthly token limit (admin only). null = unlimited."""
    _require_admin(auth)
    await container[TokenLimitStore].set(
        auth.workspace_id, None, body.limit, updated_by=auth.user_id,
    )


@router.put("/token-limits/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def set_user_token_limit(
    user_id: UUID,
    body: TokenLimitBody,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Set a per-user monthly token limit override (admin only). null = unlimited."""
    _require_admin(auth)
    await container[TokenLimitStore].set(
        auth.workspace_id, user_id, body.limit, updated_by=auth.user_id,
    )


@router.delete("/token-limits/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_token_limit(
    user_id: UUID,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> None:
    """Remove a per-user override so the user falls back to the workspace default."""
    _require_admin(auth)
    await container[TokenLimitStore].delete(auth.workspace_id, user_id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd services && uv run pytest tests/interfaces/test_token_limit_routes.py tests/interfaces/test_stats_member_usage.py tests/interfaces/test_api_routes.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add services/interfaces/api/routes/workspace_routes.py services/tests/conftest.py services/tests/interfaces/test_token_limit_routes.py services/tests/interfaces/test_stats_member_usage.py services/tests/interfaces/test_api_routes.py
git commit -m "feat(usage): admin CRUD for workspace token limits; share strip_authz_middleware"
```

---

### Task 4: 429 enforcement on chat send + upload + create

**Files:**
- Modify: `services/interfaces/api/routes/helpers.py` (429 mapping + `ensure_within_quota`)
- Modify: `services/interfaces/api/routes/chat_routes.py` (`send_message`, line ~226 + import at line 37)
- Modify: `services/interfaces/api/routes/artifact_routes.py` (`create_artifact` line ~112, `upload_blob` line ~128 + import block at line 48)
- Modify: `services/infrastructure/di/container.py` (register `CheckTokenQuotaUseCase` after the `TokenLimitStore` block from Task 1)
- Test: `services/tests/interfaces/test_quota_enforcement.py`

**Interfaces:**
- Consumes: `CheckTokenQuotaUseCase` (Task 2), `_map_app_error_to_http_exception` (exists in helpers.py).
- Produces: `ensure_within_quota(auth: RequestAuth, container: Container) -> None` in `interfaces/api/routes/helpers.py`; `"rate_limited"` AppError category → HTTP 429.

- [ ] **Step 1: Write the failing test**

Create `services/tests/interfaces/test_quota_enforcement.py`:

```python
"""429 quota enforcement on chat send + artifact upload/create."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from returns.result import Failure, Success

from application.dtos.chat_dtos import AgentEvent
from application.dtos.errors import AppError
from application.use_cases.chat_use_cases import SendMessageUseCase
from application.use_cases.token_limit_use_cases import CheckTokenQuotaUseCase
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
        {CheckTokenQuotaUseCase: quota, SendMessageUseCase: FakeSendUseCase()},
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services && uv run pytest tests/interfaces/test_quota_enforcement.py -v`
Expected: FAIL — over-limit cases don't 429 (no gate yet); import of `ensure_within_quota` not involved yet so failures are assertion errors (200/500 instead of 429)

- [ ] **Step 3: Add the 429 mapping + helper**

In `services/interfaces/api/routes/helpers.py`:

(a) In `_map_app_error_to_http_exception`, after the `"concurrency"` branch (line ~43), add:

```python
    if error.category == "rate_limited":
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error.message,
        )
```

(b) Add at the top with the other imports: `from returns.result import Failure`

(c) Append at the end of the file:

```python
async def ensure_within_quota(auth: RequestAuth, container: Container) -> None:
    """Pre-flight monthly token quota gate (chat send + upload/create).

    Admins are exempt. Raises 429 with a human-readable detail when the
    caller is over their effective monthly limit; the check itself fails
    open on infrastructure errors (see CheckTokenQuotaUseCase).
    """
    if auth.is_admin:
        return
    from application.use_cases.token_limit_use_cases import CheckTokenQuotaUseCase

    result = await container[CheckTokenQuotaUseCase].execute(auth.workspace_id, auth.user_id)
    if isinstance(result, Failure):
        raise _map_app_error_to_http_exception(result.failure())
```

- [ ] **Step 4: Wire the three routes**

In `services/interfaces/api/routes/chat_routes.py`:
- Line 37 area, add: `from interfaces.api.routes.helpers import ensure_within_quota`
- In `send_message` (line ~226), insert the gate as the first statement of the handler body, before `_get_allowed_artifact_ids`:

```python
    await ensure_within_quota(auth, container)
    allowed_artifact_ids = await _get_allowed_artifact_ids(auth)
```

In `services/interfaces/api/routes/artifact_routes.py`:
- Add `ensure_within_quota` to the existing helpers import list (line 48).
- In `create_artifact` (line ~112) and `upload_blob` (line ~128), insert directly after each `await require_action(auth, "artifacts:create")`:

```python
    await ensure_within_quota(auth, container)
```

- [ ] **Step 5: Register the use case in DI**

In `services/infrastructure/di/container.py`, directly after the `container[TokenLimitStore] = ...` block added in Task 1, add:

```python
    from application.use_cases.token_limit_use_cases import CheckTokenQuotaUseCase

    container[CheckTokenQuotaUseCase] = lambda c: CheckTokenQuotaUseCase(
        token_limit_store=c[TokenLimitStore],
        token_usage_store=c[TokenUsageStore],
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd services && uv run pytest tests/interfaces/test_quota_enforcement.py -v`
Expected: 5 PASS

Run: `cd services && uv run pytest tests/interfaces -q`
Expected: all pass (existing chat/artifact route tests unaffected — FakeAuth defaults allow actions, and existing tests' containers never reach the quota key only if admin… NOTE: if any existing non-admin chat/artifact route test now KeyErrors on `CheckTokenQuotaUseCase`, add `CheckTokenQuotaUseCase: FakeQuota(Success(None))` to that test's FakeContainer mapping — this is expected fallout of a new dependency, fix forward in those test files.)

- [ ] **Step 7: Commit**

```bash
git add services/interfaces/api/routes/helpers.py services/interfaces/api/routes/chat_routes.py services/interfaces/api/routes/artifact_routes.py services/infrastructure/di/container.py services/tests/interfaces/test_quota_enforcement.py
git commit -m "feat(usage): 429 pre-flight quota gate on chat send + artifact upload/create"
```

---

### Task 5: Extend GET /chat/usage with month + limit

**Files:**
- Modify: `services/application/dtos/usage_dtos.py` (append `MonthUsage`, `UserTokenUsageResponse`)
- Modify: `services/application/use_cases/chat_use_cases.py` (`GetUserTokenUsageUseCase`, lines 193-214)
- Modify: `services/interfaces/api/routes/chat_routes.py` (`/usage` return type, line ~130)
- Modify: `services/infrastructure/di/container.py` (line ~991, add limit-store dep)
- Test: rewrite `services/tests/application/test_chat_usage_use_case.py`

**Interfaces:**
- Consumes: `TokenLimitStore` (Task 1), `effective_limit` + `utc_month_start` (Task 2).
- Produces: `GET /chat/usage` response shape (Task 9's frontend type mirrors it exactly):
  `{"prompt": int, "completion": int, "total": int, "month": {"chat": int, "ingestion": int, "total": int, "limit": int|null}}`
  via `UserTokenUsageResponse(TokenUsageDTO)` with `month: MonthUsage`.

- [ ] **Step 1: Add the DTOs**

Append to `services/application/dtos/usage_dtos.py` (add `from application.dtos.chat_dtos import TokenUsageDTO` to its imports):

```python
class MonthUsage(BaseModel):
    """Current-calendar-month usage (UTC) + the caller's effective limit."""

    chat: int = 0
    ingestion: int = 0
    total: int = 0
    limit: int | None = None  # None = unlimited


class UserTokenUsageResponse(TokenUsageDTO):
    """GET /chat/usage: requested-window totals + current-month block."""

    month: MonthUsage
```

- [ ] **Step 2: Rewrite the use-case test**

Replace `services/tests/application/test_chat_usage_use_case.py` in full:

```python
"""GetUserTokenUsageUseCase — windowed totals + current-month block with limit."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.chat_dtos import TokenUsageDTO
from application.dtos.usage_dtos import TokenLimitEntry
from application.use_cases.chat_use_cases import GetUserTokenUsageUseCase
from application.use_cases.token_limit_use_cases import utc_month_start


class _FakeUsageStore:
    """Returns per-kind values for month queries, a default for the main window."""

    def __init__(
        self,
        default: TokenUsageDTO | None = None,
        by_kind: dict[str, TokenUsageDTO] | None = None,
        *,
        raises: bool = False,
    ) -> None:
        self._default = default or TokenUsageDTO()
        self._by_kind = by_kind or {}
        self._raises = raises
        self.calls: list[dict] = []

    async def sum_for_user(self, workspace_id, user_id, *, since=None, kind=None):
        if self._raises:
            raise RuntimeError("boom")
        self.calls.append(
            {"workspace_id": workspace_id, "user_id": user_id, "since": since, "kind": kind},
        )
        if kind in self._by_kind:
            return self._by_kind[kind]
        return self._default


class _FakeLimitStore:
    def __init__(self, rows: dict | None = None) -> None:
        self._rows = rows or {}

    async def get(self, workspace_id, user_id):
        if user_id in self._rows:
            return TokenLimitEntry(user_id=user_id, limit=self._rows[user_id])
        return None


def _uc(usage: _FakeUsageStore, rows: dict | None = None) -> GetUserTokenUsageUseCase:
    return GetUserTokenUsageUseCase(
        token_usage_store=usage, token_limit_store=_FakeLimitStore(rows),
    )


@pytest.mark.asyncio
async def test_returns_all_time_usage_plus_month_block() -> None:
    store = _FakeUsageStore(
        default=TokenUsageDTO(prompt=1000, completion=200, total=1200),
        by_kind={
            "chat": TokenUsageDTO(total=300),
            "ingestion": TokenUsageDTO(total=100),
        },
    )
    ws, owner = uuid4(), uuid4()

    result = await _uc(store, rows={None: 5000}).execute(workspace_id=ws, owner_id=owner)

    assert isinstance(result, Success)
    body = result.unwrap()
    assert (body.prompt, body.completion, body.total) == (1000, 200, 1200)
    assert body.month.chat == 300
    assert body.month.ingestion == 100
    assert body.month.total == 400
    assert body.month.limit == 5000
    # first call = requested window (all-time), then the two month/kind calls
    assert store.calls[0] == {"workspace_id": ws, "user_id": owner, "since": None, "kind": None}
    month_calls = {(c["kind"], c["since"]) for c in store.calls[1:]}
    assert month_calls == {("chat", utc_month_start()), ("ingestion", utc_month_start())}


@pytest.mark.asyncio
async def test_days_window_translates_to_since() -> None:
    store = _FakeUsageStore()
    await _uc(store).execute(workspace_id=uuid4(), owner_id=uuid4(), days=30, kind="chat")
    call = store.calls[0]
    assert call["kind"] == "chat"
    expected = datetime.now(UTC) - timedelta(days=30)
    assert abs((call["since"] - expected).total_seconds()) < 5


@pytest.mark.asyncio
async def test_no_limit_rows_means_null_limit() -> None:
    result = await _uc(_FakeUsageStore()).execute(workspace_id=uuid4(), owner_id=uuid4())
    assert result.unwrap().month.limit is None


@pytest.mark.asyncio
async def test_store_error_maps_to_failure() -> None:
    result = await _uc(_FakeUsageStore(raises=True)).execute(
        workspace_id=uuid4(), owner_id=uuid4(),
    )
    assert isinstance(result, Failure)
```

Run: `cd services && uv run pytest tests/application/test_chat_usage_use_case.py -v`
Expected: FAIL — `GetUserTokenUsageUseCase.__init__() got an unexpected keyword argument 'token_limit_store'`

- [ ] **Step 3: Extend the use case**

In `services/application/use_cases/chat_use_cases.py`, replace the `GetUserTokenUsageUseCase` class (lines 193-214) with:

```python
class GetUserTokenUsageUseCase:
    """Per-user token totals from the usage ledger + current-month block with limit."""

    def __init__(
        self,
        token_usage_store: TokenUsageStore,
        token_limit_store: TokenLimitStore,
    ) -> None:
        self._usage = token_usage_store
        self._limits = token_limit_store

    async def execute(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        days: int | None = None,
        kind: str | None = None,
    ) -> Result[UserTokenUsageResponse, AppError]:
        try:
            since = datetime.now(UTC) - timedelta(days=days) if days else None
            usage = await self._usage.sum_for_user(
                workspace_id, owner_id, since=since, kind=kind,
            )
            month_since = utc_month_start()
            month_chat = await self._usage.sum_for_user(
                workspace_id, owner_id, since=month_since, kind="chat",
            )
            month_ingestion = await self._usage.sum_for_user(
                workspace_id, owner_id, since=month_since, kind="ingestion",
            )
            limit = await effective_limit(self._limits, workspace_id, owner_id)
            return Success(
                UserTokenUsageResponse(
                    prompt=usage.prompt,
                    completion=usage.completion,
                    total=usage.total,
                    month=MonthUsage(
                        chat=month_chat.total,
                        ingestion=month_ingestion.total,
                        total=month_chat.total + month_ingestion.total,
                        limit=limit,
                    ),
                ),
            )
        except Exception as e:
            log.exception("chat.usage.get_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to get token usage: {e!s}"))
```

Add to that file's imports:

```python
from application.dtos.usage_dtos import MonthUsage, UserTokenUsageResponse
from application.ports.token_limit_store import TokenLimitStore
from application.use_cases.token_limit_use_cases import effective_limit, utc_month_start
```

- [ ] **Step 4: Update route annotation + DI**

In `services/interfaces/api/routes/chat_routes.py`: change the `/usage` endpoint's return annotation (line ~130) from `-> TokenUsageDTO` to `-> UserTokenUsageResponse` and add `from application.dtos.usage_dtos import UserTokenUsageResponse` to the imports (keep the `TokenUsageDTO` import only if still referenced elsewhere in the file; remove it if unused).

In `services/infrastructure/di/container.py` (line ~991):

```python
    container[GetUserTokenUsageUseCase] = lambda c: GetUserTokenUsageUseCase(
        token_usage_store=c[TokenUsageStore],
        token_limit_store=c[TokenLimitStore],
    )
```

(`TokenLimitStore` is imported ~140 lines above by Task 1's block inside the same function; if the name isn't in scope at line 991, re-import it locally next to this registration.)

- [ ] **Step 5: Run tests + full suite**

Run: `cd services && uv run pytest tests/application/test_chat_usage_use_case.py -v`
Expected: 4 PASS

Run: `cd services && uv run pytest -q`
Expected: full suite green (baseline was 538 + new tests)

- [ ] **Step 6: Commit**

```bash
git add services/application/dtos/usage_dtos.py services/application/use_cases/chat_use_cases.py services/interfaces/api/routes/chat_routes.py services/infrastructure/di/container.py services/tests/application/test_chat_usage_use_case.py
git commit -m "feat(usage): GET /chat/usage returns current-month usage + effective limit"
```

---

### Task 6: Settings layout + General/Chat/Workspace sub-routes

**Files:**
- Create: `web/apps/portal/src/app/[workspace]/settings/layout.tsx`
- Create: `web/apps/portal/src/app/[workspace]/settings/general/page.tsx`
- Create: `web/apps/portal/src/app/[workspace]/settings/chat/page.tsx`
- Create: `web/apps/portal/src/app/[workspace]/settings/workspace/page.tsx`
- Replace: `web/apps/portal/src/app/[workspace]/settings/page.tsx` (redirect to `./general`)

**Interfaces:**
- Consumes: existing stores/components (`useThemeStore`, `useFontFamilyStore`, `useDevModeStore`, `useScopeStore`, `ReasoningSettings`, `useSession`, `usePlugins`, `Card`/`CardHeader`, `ToggleGroup`).
- Produces: `TABS` / `ADMIN_TABS` arrays in `layout.tsx` — Tasks 7/8/9 append entries `{ label, segment }` to them. Rail hides `ADMIN_TABS` behind `useAuthzHasRole("admin")`.

- [ ] **Step 1: Create the layout**

Create `web/apps/portal/src/app/[workspace]/settings/layout.tsx`:

```tsx
"use client";

import { Settings } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useAuthzHasRole } from "@sentinel-auth/react";

import { PageHeader } from "@/components/ui/PageHeader";

interface SettingsTab {
  label: string;
  segment: string;
}

const TABS: SettingsTab[] = [
  { label: "General", segment: "general" },
  { label: "Chat", segment: "chat" },
  { label: "Workspace", segment: "workspace" },
];

const ADMIN_TABS: SettingsTab[] = [];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { workspace } = useParams<{ workspace: string }>();
  const isAdmin = useAuthzHasRole("admin");

  const base = `/${workspace}/settings`;

  const renderTab = ({ label, segment }: SettingsTab) => {
    const href = `${base}/${segment}`;
    const active = pathname.startsWith(href);
    return (
      <Link
        key={segment}
        href={href}
        className={`rounded-lg px-3 py-2 text-sm transition-colors ${
          active
            ? "bg-surface-sunken font-medium text-text-primary"
            : "text-text-muted hover:bg-surface-sunken/60 hover:text-text-primary"
        }`}
      >
        {label}
      </Link>
    );
  };

  return (
    <div>
      <PageHeader
        icon={Settings}
        title="Settings"
        subtitle="Workspace preferences and administration"
      />
      <div className="flex gap-8">
        <nav className="flex w-44 shrink-0 flex-col gap-0.5">
          {TABS.map(renderTab)}
          {isAdmin && ADMIN_TABS.length > 0 && (
            <>
              <div className="my-2 border-t border-border-default" />
              {ADMIN_TABS.map(renderTab)}
            </>
          )}
        </nav>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create the General page**

Create `web/apps/portal/src/app/[workspace]/settings/general/page.tsx` (JSX copied verbatim from the old settings page's Appearance + Developer Mode cards):

```tsx
"use client";

import { Sun, Moon, Code, Type } from "lucide-react";

import { Card, CardHeader } from "@/components/ui/Card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useThemeStore } from "@/lib/stores/theme-store";
import { useDevModeStore } from "@/lib/stores/dev-mode-store";
import { useFontFamilyStore } from "@/lib/stores/font-family-store";

const THEME_OPTIONS = [
  { label: "Light", value: "light" as const, icon: Sun },
  { label: "Dark", value: "dark" as const, icon: Moon },
];

const FONT_OPTIONS = [
  { label: "Overused Grotesk", value: "grotesk" as const, icon: Type },
  { label: "IBM Plex", value: "plex" as const, icon: Type },
  { label: "Inter", value: "inter" as const, icon: Type },
];

export default function GeneralSettingsPage() {
  const { theme, setTheme } = useThemeStore();
  const { enabled: devMode, setEnabled: setDevMode } = useDevModeStore();
  const { font, setFont } = useFontFamilyStore();

  return (
    <div className="max-w-2xl space-y-6">
      <Card>
        <CardHeader title="Appearance" />
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={theme}
          onValueChange={(nv) => {
            if (nv) setTheme(nv as "light" | "dark");
          }}
        >
          {THEME_OPTIONS.map(({ value, label, icon: Icon }) => (
            <ToggleGroupItem key={value} value={value}>
              <span className="flex items-center gap-2">
                <Icon className="h-4 w-4" />
                {label}
              </span>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>

        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          className="mt-4"
          value={font}
          onValueChange={(nv) => {
            if (nv) setFont(nv as "plex" | "inter" | "grotesk");
          }}
        >
          {FONT_OPTIONS.map(({ value, label, icon: Icon }) => (
            <ToggleGroupItem key={value} value={value}>
              <span className="flex items-center gap-2">
                <Icon className="h-4 w-4" />
                {label}
              </span>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Card>

      <Card>
        <CardHeader title="Developer Mode" />
        <p className="mb-3 text-xs text-text-muted">
          Show debug overlays with scoring details, RRF breakdowns, and pipeline diagnostics across the UI.
        </p>
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={devMode ? "on" : "off"}
          onValueChange={(nv) => {
            if (nv) setDevMode(nv === "on");
          }}
        >
          <ToggleGroupItem value="off">
            <span className="flex items-center gap-2">
              <Code className="h-4 w-4" />
              Off
            </span>
          </ToggleGroupItem>
          <ToggleGroupItem value="on">
            <span className="flex items-center gap-2">
              <Code className="h-4 w-4" />
              On
            </span>
          </ToggleGroupItem>
        </ToggleGroup>
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: Create the Chat page**

Create `web/apps/portal/src/app/[workspace]/settings/chat/page.tsx`:

```tsx
"use client";

import { Globe, Lock } from "lucide-react";

import { Card, CardHeader } from "@/components/ui/Card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { ReasoningSettings } from "@/components/chat/ReasoningSettings";
import { useScopeStore } from "@/lib/stores/scope-store";

const SCOPE_OPTIONS = [
  { label: "Workspace", value: "workspace" as const, icon: Globe },
  { label: "Private", value: "private" as const, icon: Lock },
];

export default function ChatSettingsPage() {
  const { defaultScope, setDefaultScope } = useScopeStore();

  return (
    <div className="max-w-2xl space-y-6">
      <ReasoningSettings />

      <Card>
        <CardHeader title="Default Visibility" />
        <p className="mb-3 text-xs text-text-muted">
          New documents will be created with this visibility by default.
        </p>
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={defaultScope}
          onValueChange={(nv) => {
            if (nv) setDefaultScope(nv as "workspace" | "private");
          }}
        >
          {SCOPE_OPTIONS.map(({ value, label, icon: Icon }) => (
            <ToggleGroupItem key={value} value={value}>
              <span className="flex items-center gap-2">
                <Icon className="h-4 w-4" />
                {label}
              </span>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Create the Workspace page**

Create `web/apps/portal/src/app/[workspace]/settings/workspace/page.tsx` (Workspace info + Plugins + API Keys placeholder; the "Members" placeholder card is dropped — superseded by Token Settings):

```tsx
"use client";

import { Plug, CheckCircle, Loader2 } from "lucide-react";

import { Card, CardHeader } from "@/components/ui/Card";
import { useSession } from "@/lib/auth";
import { usePlugins } from "@/plugins";

export default function WorkspaceSettingsPage() {
  const { workspace } = useSession();
  const { plugins, isLoading: pluginsLoading } = usePlugins();

  return (
    <div className="max-w-2xl space-y-6">
      <Card>
        <CardHeader title="Workspace" />
        <div className="space-y-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-text-muted">Name</span>
            <span className="text-text-primary">{workspace.name}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-muted">Slug</span>
            <span className="font-mono text-text-primary">{workspace.slug}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-muted">ID</span>
            <span className="font-mono text-text-muted">{workspace.id}</span>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader title="Plugins" />
        {pluginsLoading ? (
          <div className="flex items-center gap-2 py-2">
            <Loader2 className="size-5 animate-spin text-text-muted" />
            <span className="text-sm text-text-muted">Loading plugins…</span>
          </div>
        ) : plugins.length === 0 ? (
          <p className="text-sm text-text-muted">No plugins enabled.</p>
        ) : (
          <div className="space-y-3">
            {plugins.map((p) => (
              <div
                key={p.name}
                className="flex items-start gap-3 rounded-lg border border-border-default bg-surface-elevated px-3 py-2.5"
              >
                <Plug className="mt-0.5 h-4 w-4 shrink-0 text-text-muted" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-text-primary">
                      {p.name.replace(/_/g, " ")}
                    </span>
                    <span className="font-mono text-xs text-text-muted">v{p.version}</span>
                  </div>
                  {p.description && (
                    <p className="mt-0.5 text-xs text-text-muted">{p.description}</p>
                  )}
                </div>
                <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-ds-success" />
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="API Keys" />
        <p className="text-sm text-text-muted">API key management is coming soon.</p>
      </Card>
    </div>
  );
}
```

- [ ] **Step 5: Replace the settings index with a redirect**

Replace `web/apps/portal/src/app/[workspace]/settings/page.tsx` in full:

```tsx
import { redirect } from "next/navigation";

export default async function SettingsIndex({
  params,
}: {
  params: Promise<{ workspace: string }>;
}) {
  const { workspace } = await params;
  redirect(`/${workspace}/settings/general`);
}
```

- [ ] **Step 6: Type-check and build**

Run: `cd web && pnpm --filter portal lint`
Expected: no errors

Run: `cd web && pnpm --filter portal build`
Expected: build succeeds (commit `next-env.d.ts` if Next regenerates it)

- [ ] **Step 7: Commit**

```bash
git add web/apps/portal/src/app
git commit -m "feat(web): settings as sub-route tabs — layout rail + general/chat/workspace"
```

---

### Task 7: Move Stats + Status under settings, redirects, sidebar cleanup

**Files:**
- Create: `web/apps/portal/src/components/settings/SettingsSectionHeader.tsx`
- Move: `web/apps/portal/src/app/[workspace]/stats/page.tsx` → `web/apps/portal/src/app/[workspace]/settings/stats/page.tsx`
- Move: `web/apps/portal/src/app/[workspace]/status/{page.tsx,WorkersSection.tsx,WorkerCard.tsx,status-helpers.ts}` → `web/apps/portal/src/app/[workspace]/settings/status/`
- Create (replacing moved files): redirect pages at the old `stats/page.tsx` and `status/page.tsx` paths
- Modify: `web/apps/portal/src/app/[workspace]/settings/layout.tsx` (add ADMIN_TABS entries)
- Modify: `web/apps/portal/src/components/layout/Sidebar.tsx` (drop Stats/Status + dead code)

**Interfaces:**
- Consumes: `TABS`/`ADMIN_TABS` from Task 6's layout.
- Produces: `SettingsSectionHeader({ title, subtitle?, badge?, actions? })` in `components/settings/`; routes `/[workspace]/settings/stats` and `/[workspace]/settings/status`.

- [ ] **Step 1: Create the section header**

Create `web/apps/portal/src/components/settings/SettingsSectionHeader.tsx` (an `h2`-level stand-in for `PageHeader` inside settings tabs — the layout owns the page's `h1`):

```tsx
import type { ReactNode } from "react";

export function SettingsSectionHeader({
  title,
  subtitle,
  badge,
  actions,
}: {
  title: string;
  subtitle?: string;
  badge?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
          {badge}
        </div>
        {subtitle && <p className="mt-0.5 text-sm text-text-secondary">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
```

- [ ] **Step 2: Move the pages**

```bash
cd web/apps/portal/src/app/[workspace]
mkdir -p settings/stats settings/status
git mv stats/page.tsx settings/stats/page.tsx
git mv status/page.tsx settings/status/page.tsx
git mv status/WorkersSection.tsx settings/status/WorkersSection.tsx
git mv status/WorkerCard.tsx settings/status/WorkerCard.tsx
git mv status/status-helpers.ts settings/status/status-helpers.ts
```

(All non-relative imports in these files use `@/` aliases, and status's relative imports move together — no import rewrites needed beyond the header swap below.)

- [ ] **Step 3: Swap PageHeader → SettingsSectionHeader in the moved pages**

In `settings/stats/page.tsx` and `settings/status/page.tsx`:
- Replace the import `import { PageHeader } from "@/components/ui/PageHeader";` with `import { SettingsSectionHeader } from "@/components/settings/SettingsSectionHeader";`
- Replace every `<PageHeader` JSX usage (3 sites per file: loading, error, main) with `<SettingsSectionHeader`, **dropping the `icon={...}` prop** and keeping `title`/`subtitle`/`badge`/`actions` as-is. Remove the now-unused header icon imports (`BarChart3` in stats, `Activity` in status) **only if** nothing else in the file uses them (search first — stats may use them in stat cards).
- Keep each page's `useAuthzHasRole("admin")` Access-Denied `EmptyState` gate — it now protects direct URL hits.

- [ ] **Step 4: Create the old-route redirects**

Create `web/apps/portal/src/app/[workspace]/stats/page.tsx`:

```tsx
import { redirect } from "next/navigation";

export default async function StatsRedirect({
  params,
}: {
  params: Promise<{ workspace: string }>;
}) {
  const { workspace } = await params;
  redirect(`/${workspace}/settings/stats`);
}
```

Create `web/apps/portal/src/app/[workspace]/status/page.tsx`:

```tsx
import { redirect } from "next/navigation";

export default async function StatusRedirect({
  params,
}: {
  params: Promise<{ workspace: string }>;
}) {
  const { workspace } = await params;
  redirect(`/${workspace}/settings/status`);
}
```

- [ ] **Step 5: Add the admin tabs**

In `settings/layout.tsx`, set:

```tsx
const ADMIN_TABS: SettingsTab[] = [
  { label: "Stats", segment: "stats" },
  { label: "Status", segment: "status" },
];
```

- [ ] **Step 6: Clean up the Sidebar**

In `web/apps/portal/src/components/layout/Sidebar.tsx`:
- Delete the two `mainNav` entries for Stats and Status (lines 42-43).
- Delete `requireAdmin?: boolean;` from the `NavItem` interface, and simplify line 92 `mainNav.filter((item) => !item.requireAdmin || isAdmin).map(...)` → `mainNav.map(...)`.
- Delete `const isAdmin = useAuthzHasRole("admin");` (line 50) and the `import { useAuthzHasRole } from "@sentinel-auth/react";` (line 19).
- Remove `Activity` and `BarChart3` from the lucide import (lines 10-11).

Then check for other hardcoded links to the old routes:

```bash
cd web && grep -rn '"/stats"\|"/status"\|/stats\`\|/status\`' apps/portal/src --include="*.tsx" --include="*.ts"
```

Update any hits (outside the redirect files themselves) to point at `/settings/stats` / `/settings/status`.

- [ ] **Step 7: Type-check, build, commit**

Run: `cd web && pnpm --filter portal lint && pnpm --filter portal build`
Expected: green

```bash
git add web/apps/portal/src
git commit -m "feat(web): move Stats + Status into settings tabs; redirect old routes"
```

---

### Task 8: Token Settings tab (admin)

**Files:**
- Modify: `web/apps/portal/src/lib/query-keys.ts` (workspace group, line ~114)
- Create: `web/apps/portal/src/hooks/use-token-limits.ts`
- Create: `web/apps/portal/src/app/[workspace]/settings/tokens/page.tsx`
- Modify: `web/apps/portal/src/app/[workspace]/settings/layout.tsx` (add tab)

**Interfaces:**
- Consumes: Task 3 endpoints; existing `useWorkspaceMembers()` + `useMemberUsageStats("month")` from `hooks/use-stats.ts`; `formatTokens` from `@/lib/utils`; `authFetch`/`authFetchJson` from `@/lib/auth-fetch`.
- Produces: `useWorkspaceTokenLimits()`, `useSetDefaultTokenLimit()`, `useSetUserTokenLimit()`, `useClearUserTokenLimit()`; `queryKeys.workspace.tokenLimits()`.

- [ ] **Step 1: Add the query key**

In `web/apps/portal/src/lib/query-keys.ts`, inside the `workspace` group (line ~114-116), add:

```ts
    tokenLimits: () => [...queryKeys.workspace.all, "token-limits"] as const,
```

- [ ] **Step 2: Create the hooks**

Create `web/apps/portal/src/hooks/use-token-limits.ts`:

```ts
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { authFetch, authFetchJson } from "@/lib/auth-fetch";
import { queryKeys } from "@/lib/query-keys";

export interface TokenLimitOverride {
  user_id: string;
  limit: number | null;
}

export interface WorkspaceTokenLimits {
  default_limit: number | null;
  overrides: TokenLimitOverride[];
}

/** PUT/DELETE return 204 (no body) — authFetchJson would choke on the empty body. */
async function limitRequest(path: string, init: RequestInit): Promise<void> {
  const res = await authFetch(path, init);
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // non-JSON error body
    }
    throw new Error(detail ?? `Request failed (${res.status})`);
  }
}

export function useWorkspaceTokenLimits() {
  return useQuery({
    queryKey: queryKeys.workspace.tokenLimits(),
    queryFn: () => authFetchJson<WorkspaceTokenLimits>("/workspace/token-limits"),
  });
}

function useInvalidateLimits() {
  const queryClient = useQueryClient();
  return () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.workspace.tokenLimits() });
}

export function useSetDefaultTokenLimit() {
  const invalidate = useInvalidateLimits();
  return useMutation({
    mutationFn: (limit: number | null) =>
      limitRequest("/workspace/token-limits/default", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit }),
      }),
    onSuccess: invalidate,
  });
}

export function useSetUserTokenLimit() {
  const invalidate = useInvalidateLimits();
  return useMutation({
    mutationFn: ({ userId, limit }: { userId: string; limit: number | null }) =>
      limitRequest(`/workspace/token-limits/${userId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit }),
      }),
    onSuccess: invalidate,
  });
}

export function useClearUserTokenLimit() {
  const invalidate = useInvalidateLimits();
  return useMutation({
    mutationFn: (userId: string) =>
      limitRequest(`/workspace/token-limits/${userId}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}
```

- [ ] **Step 3: Create the page**

Create `web/apps/portal/src/app/[workspace]/settings/tokens/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { ShieldAlert } from "lucide-react";
import { useAuthzHasRole } from "@sentinel-auth/react";

import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { useMemberUsageStats, useWorkspaceMembers } from "@/hooks/use-stats";
import {
  useClearUserTokenLimit,
  useSetDefaultTokenLimit,
  useSetUserTokenLimit,
  useWorkspaceTokenLimits,
} from "@/hooks/use-token-limits";
import { formatTokens } from "@/lib/utils";

function limitLabel(limit: number | null): string {
  return limit === null ? "Unlimited" : formatTokens(limit);
}

/** Parse the shared limit input: "" = unlimited (null), else a non-negative int. */
function parseLimitInput(raw: string): number | null | undefined {
  if (raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isInteger(n) && n >= 0 ? n : undefined;
}

function LimitInput({
  onSave,
  isPending,
  placeholder,
}: {
  onSave: (limit: number | null) => void;
  isPending: boolean;
  placeholder: string;
}) {
  const [value, setValue] = useState("");
  const parsed = parseLimitInput(value);
  return (
    <span className="flex items-center gap-2">
      <input
        type="number"
        min={0}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        className="w-32 rounded-md border border-border-default bg-surface-elevated px-2 py-1 font-mono text-xs text-text-primary"
      />
      <button
        onClick={() => {
          if (parsed !== undefined) {
            onSave(parsed);
            setValue("");
          }
        }}
        disabled={isPending || parsed === undefined}
        className="rounded-md border border-border-default px-2 py-1 text-xs text-text-primary hover:bg-surface-sunken disabled:opacity-50"
      >
        Set
      </button>
    </span>
  );
}

export default function TokenSettingsPage() {
  const isAdmin = useAuthzHasRole("admin");
  const limits = useWorkspaceTokenLimits();
  const members = useWorkspaceMembers();
  const usage = useMemberUsageStats("month");
  const setDefault = useSetDefaultTokenLimit();
  const setUser = useSetUserTokenLimit();
  const clearUser = useClearUserTokenLimit();

  if (!isAdmin) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Access Denied"
        description="You need admin privileges to manage token limits."
      />
    );
  }

  const defaultLimit = limits.data?.default_limit ?? null;
  const overrideByUser = new Map(
    (limits.data?.overrides ?? []).map((o) => [o.user_id, o.limit]),
  );
  const usageByUser = new Map(
    (usage.data?.members ?? []).map((m) => [m.user_id, m.total_tokens]),
  );

  return (
    <div className="max-w-4xl space-y-6">
      <Card>
        <CardHeader title="Workspace Default" />
        <p className="mb-3 text-xs text-text-muted">
          Monthly token budget applied to every member without an override. Empty = unlimited.
          Usage resets on the 1st (UTC). Admins are exempt from enforcement.
        </p>
        <div className="flex items-center gap-4 text-sm">
          <span className="font-mono text-text-primary">{limitLabel(defaultLimit)}</span>
          <LimitInput
            onSave={(limit) => setDefault.mutate(limit)}
            isPending={setDefault.isPending}
            placeholder="e.g. 5000000"
          />
        </div>
        {setDefault.isError && (
          <p className="mt-2 text-xs text-red-500">{setDefault.error.message}</p>
        )}
      </Card>

      <Card>
        <CardHeader title="Member Limits" />
        {members.isLoading || limits.isLoading ? (
          <p className="text-sm text-text-muted">Loading members…</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-default text-left text-xs text-text-muted">
                <th className="py-2 font-medium">Member</th>
                <th className="py-2 font-medium">This month</th>
                <th className="py-2 font-medium">Limit</th>
                <th className="py-2 font-medium">Override</th>
              </tr>
            </thead>
            <tbody>
              {(members.data ?? []).map((m) => {
                const userId = m.user_id ?? m.id ?? "";
                const hasOverride = overrideByUser.has(userId);
                const effective = hasOverride ? overrideByUser.get(userId)! : defaultLimit;
                return (
                  <tr key={userId} className="border-b border-border-default/50">
                    <td className="py-2">
                      <div className="text-text-primary">{m.name ?? "Unknown"}</div>
                      <div className="text-xs text-text-muted">{m.email ?? userId}</div>
                    </td>
                    <td className="py-2 font-mono text-text-primary">
                      {formatTokens(usageByUser.get(userId) ?? 0)}
                    </td>
                    <td className="py-2">
                      <span className="font-mono text-text-primary">
                        {limitLabel(effective)}
                      </span>{" "}
                      <span className="text-xs text-text-muted">
                        {hasOverride ? "override" : "default"}
                      </span>
                    </td>
                    <td className="py-2">
                      <span className="flex items-center gap-2">
                        <LimitInput
                          onSave={(limit) => setUser.mutate({ userId, limit })}
                          isPending={setUser.isPending}
                          placeholder="tokens"
                        />
                        {hasOverride && (
                          <button
                            onClick={() => clearUser.mutate(userId)}
                            disabled={clearUser.isPending}
                            className="text-xs text-text-muted underline hover:text-text-primary disabled:opacity-50"
                          >
                            Clear
                          </button>
                        )}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {(setUser.isError || clearUser.isError) && (
          <p className="mt-2 text-xs text-red-500">
            {setUser.error?.message ?? clearUser.error?.message}
          </p>
        )}
        <p className="mt-3 text-xs text-text-muted">
          Member list is capped at 50 (same as the stats member card). Setting a member's
          override to empty saves an explicit Unlimited that beats the workspace default.
        </p>
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Add the tab**

In `settings/layout.tsx`, prepend to `ADMIN_TABS`:

```tsx
const ADMIN_TABS: SettingsTab[] = [
  { label: "Token Settings", segment: "tokens" },
  { label: "Stats", segment: "stats" },
  { label: "Status", segment: "status" },
];
```

- [ ] **Step 5: Type-check, build, commit**

Run: `cd web && pnpm --filter portal lint && pnpm --filter portal build`
Expected: green

```bash
git add web/apps/portal/src
git commit -m "feat(web): Token Settings tab — workspace default + per-member limit overrides"
```

---

### Task 9: Usage tab + Topbar badge + shared type

**Files:**
- Modify: `web/packages/types/src/domain/chat.ts` (after `TokenUsage`, line ~67)
- Modify: `web/apps/portal/src/hooks/use-usage.ts`
- Modify: `web/apps/portal/src/components/layout/Topbar.tsx` (badge block, lines 99-107)
- Create: `web/apps/portal/src/app/[workspace]/settings/usage/page.tsx`
- Modify: `web/apps/portal/src/app/[workspace]/settings/layout.tsx` (add tab)

**Interfaces:**
- Consumes: Task 5's response shape (`month: {chat, ingestion, total, limit}`); `formatTokens` from `@/lib/utils`.
- Produces: `MonthTokenUsage` + `UserTokenUsage` types in `@docu-store/types`; `useUserTokenUsage()` now returns `UserTokenUsage`.

> Skill note for the implementer: the Usage tab renders a meter (progress bar + stat tiles) — invoke the `dataviz` skill before writing that markup, then keep to the palette rule in Global Constraints.

- [ ] **Step 1: Extend the types**

In `web/packages/types/src/domain/chat.ts`, directly after the `TokenUsage` interface (line ~67-72), add:

```ts
export interface MonthTokenUsage {
  chat: number;
  ingestion: number;
  total: number;
  limit: number | null;
}

/** GET /chat/usage — requested-window totals + current-calendar-month block. */
export interface UserTokenUsage extends TokenUsage {
  month: MonthTokenUsage;
}
```

(`ChatMessage.token_usage` keeps plain `TokenUsage` — messages have no month block.)

- [ ] **Step 2: Update the hook**

In `web/apps/portal/src/hooks/use-usage.ts`: change the import to `import type { UserTokenUsage } from "@docu-store/types";` and the fetch to `authFetchJson<UserTokenUsage>("/chat/usage")`. Update the doc comment to mention the month block.

- [ ] **Step 3: Update the Topbar badge**

In `web/apps/portal/src/components/layout/Topbar.tsx`, replace the badge block (lines 99-107) with:

```tsx
        {usage.data && (usage.data.month.total > 0 || usage.data.month.limit !== null) && (
          <TokenBadge month={usage.data.month} />
        )}
```

and add this component at the bottom of the file (plus `import type { MonthTokenUsage } from "@docu-store/types";` at the top):

```tsx
function TokenBadge({ month }: { month: MonthTokenUsage }) {
  const pct = month.limit ? month.total / month.limit : null;
  const color =
    pct !== null && pct >= 1
      ? "text-red-500"
      : pct !== null && pct >= 0.8
        ? "text-amber-500"
        : "text-text-muted";
  return (
    <span
      className={`hidden md:inline-flex items-center gap-1 px-2 text-xs font-mono tabular-nums ${color}`}
      title={`${month.total.toLocaleString()} tokens this month${
        month.limit !== null ? ` of ${month.limit.toLocaleString()} limit` : ""
      } — resets on the 1st (UTC)`}
    >
      <Coins className="size-3 text-amber-500" />
      {formatTokens(month.total)}
      {month.limit !== null && ` / ${formatTokens(month.limit)}`}
    </span>
  );
}
```

- [ ] **Step 4: Create the Usage page**

Create `web/apps/portal/src/app/[workspace]/settings/usage/page.tsx`:

```tsx
"use client";

import { Coins } from "lucide-react";

import { Card, CardHeader } from "@/components/ui/Card";
import { useUserTokenUsage } from "@/hooks/use-usage";
import { formatTokens } from "@/lib/utils";

export default function UsageSettingsPage() {
  const usage = useUserTokenUsage();
  const month = usage.data?.month;

  const pct = month?.limit ? Math.min(month.total / month.limit, 1) : null;
  const barColor =
    pct === null
      ? ""
      : pct >= 1
        ? "bg-red-500"
        : pct >= 0.8
          ? "bg-amber-500"
          : "bg-emerald-500";

  return (
    <div className="max-w-2xl space-y-6">
      <Card>
        <CardHeader title="This Month" />
        {!month ? (
          <p className="text-sm text-text-muted">Loading usage…</p>
        ) : (
          <div className="space-y-4">
            <div className="flex items-baseline justify-between">
              <span className="flex items-center gap-2 text-sm text-text-muted">
                <Coins className="size-4 text-amber-500" />
                {month.limit !== null
                  ? `${formatTokens(month.total)} of ${formatTokens(month.limit)} tokens`
                  : `${formatTokens(month.total)} tokens (no limit set)`}
              </span>
              {pct !== null && (
                <span className="font-mono text-xs text-text-muted">
                  {Math.round(pct * 100)}%
                </span>
              )}
            </div>
            {pct !== null && (
              <div className="h-2 w-full overflow-hidden rounded-full bg-surface-sunken">
                <div
                  className={`h-full rounded-full ${barColor}`}
                  style={{ width: `${pct * 100}%` }}
                />
              </div>
            )}
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="rounded-lg border border-border-default px-3 py-2.5">
                <div className="text-xs text-text-muted">Chat</div>
                <div className="font-mono text-text-primary">{formatTokens(month.chat)}</div>
              </div>
              <div className="rounded-lg border border-border-default px-3 py-2.5">
                <div className="text-xs text-text-muted">Document processing</div>
                <div className="font-mono text-text-primary">
                  {formatTokens(month.ingestion)}
                </div>
              </div>
            </div>
            <p className="text-xs text-text-muted">
              Usage resets on the 1st of each month (UTC). Chat and document processing both
              count toward your limit.
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}
```

- [ ] **Step 5: Add the tab**

In `settings/layout.tsx`, add Usage to `TABS` (between Chat and Workspace):

```tsx
const TABS: SettingsTab[] = [
  { label: "General", segment: "general" },
  { label: "Chat", segment: "chat" },
  { label: "Usage", segment: "usage" },
  { label: "Workspace", segment: "workspace" },
];
```

- [ ] **Step 6: Type-check, build, commit**

Run: `cd web && pnpm --filter portal lint && pnpm --filter portal build`
Expected: green

```bash
git add web/apps/portal/src web/packages/types/src
git commit -m "feat(web): Usage settings tab + month/limit-aware topbar token badge"
```

---

### Task 10: Chat over-limit surfacing + full verification

**Files:**
- Modify: `web/apps/portal/src/hooks/use-chat.ts` (the `!res.ok` branch, lines 157-160)

**Interfaces:**
- Consumes: Task 4's 429 with string `detail`; existing `store.appendToken` error-rendering path (same one SSE `error` events use at use-chat.ts:347-349).

- [ ] **Step 1: Surface the 429 detail in-thread**

In `web/apps/portal/src/hooks/use-chat.ts`, replace:

```ts
      if (!res.ok) {
        store.finishStreaming();
        throw new Error(`Chat failed: ${res.statusText}`);
      }
```

with:

```ts
      if (!res.ok) {
        let detail: string | undefined;
        try {
          const body = (await res.json()) as { detail?: unknown };
          if (typeof body?.detail === "string") detail = body.detail;
        } catch {
          // non-JSON error body — fall back to statusText
        }
        const message = detail ?? `Chat failed: ${res.statusText}`;
        // Render in-thread via the same path SSE error events use.
        store.appendToken(`\n\n**Error:** ${message}`);
        store.finishStreaming();
        throw new Error(message);
      }
```

- [ ] **Step 2: Full backend suite**

Run: `cd services && uv run pytest -q`
Expected: all green

- [ ] **Step 3: Full frontend check**

Run: `cd web && pnpm --filter portal lint && pnpm --filter portal build`
Expected: green

- [ ] **Step 4: Manual browser verification**

Start the stack (per repo runbook): `cd services && make docker-up`, then `PORT=8010 make run-all`; `cd web && pnpm --filter portal dev` (:15000). Then verify:

1. Sidebar no longer shows Stats/Status; `/{ws}/stats` and `/{ws}/status` redirect into settings.
2. `/{ws}/settings` redirects to General; rail shows General/Chat/Usage/Workspace (+ admin section for admins); as a non-admin (Sentinel viewer/editor account) the admin section is absent and direct URLs to tokens/stats/status show Access Denied.
3. Token Settings: set workspace default to a small number (e.g. `1000`); table shows members with month usage; set + clear a per-user override.
4. As a non-admin over the limit: chat send shows `**Error:** Monthly token limit reached: …` in-thread; document upload row shows the same detail message.
5. Topbar badge shows `used / limit` and turns amber/red at 80%/100%; Usage tab bar matches.
6. Reset the default back to Unlimited (empty input → Set).

- [ ] **Step 5: Commit**

```bash
git add web/apps/portal/src/hooks/use-chat.ts
git commit -m "feat(web): surface chat 429 quota errors in-thread with backend detail"
```

---

## Post-plan notes

- Deploy sequencing lives in the spec §G: `token-limits` merges after (or with) `token-usage-ledger`; remember the unrelated NER fix `134aa7a` cherry-pick decision before merging the ledger branch.
- No data migration: absent limit rows = unlimited = today's behavior.
