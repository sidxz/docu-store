# Token Usage Accounting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make token accounting real, durable, and user-attributed everywhere an LLM is called — chat *and* ingestion — so per-user token limits can be enforced later, and admins can see per-member usage.

**Architecture:** A new append-only MongoDB ledger (`token_usage_events`) becomes the source of truth for token accounting. The existing contextvar `TokenCounter` (which already harvests real provider-reported usage via a LangChain `on_llm_end` callback) gains identity fields; ownership of the counter moves from the chat agents up into `SendMessageUseCase`, which writes one ledger event per turn in a `finally` (so errors and client disconnects still record). The three ingestion LLM use cases wrap their calls in the same counter and record ledger events attributed via the already-loaded `Artifact` aggregate. Langfuse traces get user/session attribution through the same counter via the v3 `langfuse_*` metadata keys.

**Tech Stack:** Python 3.12, FastAPI, Motor (async MongoDB), LangChain callbacks, Langfuse v3 SDK (installed: 3.14.5), pydantic v2, pytest + pytest-asyncio. Frontend: Next.js 16, TanStack Query v5.

## Fixes delivered (from the 2026-07-13 audit)

| Hole | Fix | Task |
|---|---|---|
| 1. Streamed-chunk-count estimate fallback in agents' done event | Deleted; done event reports provider counts only | 3 |
| 2. Deleting a conversation erases recorded usage (quota evasion) | Append-only ledger independent of chat CRUD; badge reads ledger | 1, 3, 4 |
| 3. Usage lost on mid-stream disconnect / pipeline error | Single write point in `finally`, `asyncio.shield`-protected | 3 |
| 4. Per-user usage is all-time, aggregate-on-read `$lookup` | Ledger indexed `(workspace_id, user_id, created_at)`; windowed `sum_for_user` | 1, 4 |
| 6. Langfuse traces anonymous | `langfuse_user_id` / `langfuse_session_id` / `langfuse_tags` metadata from active counter | 2 |
| Ingestion counts nothing | Page summary, artifact summary, doc-metadata fallback wrapped + recorded (`kind="ingestion"`) | 5 |
| Admin can't see per-member usage | `GET /stats/member-usage` + stats-page card (chat vs ingestion split) | 6, 7 |

## Global Constraints

- **Out of scope:** NER token counting (structflo-ner → langextract exposes no usage; deferred by decision). Quota *enforcement* (this plan builds the accounting it will need). CSER/GLiNER2/embeddings are local models — no tokens exist to count.
- All Python commands via `uv run` (never bare `python`/`pytest`). Test suite: `cd services && uv run pytest tests/ -q` — must be green at the end of every task.
- No new dependencies. Python 3.12 syntax (`X | None`, no `Optional`).
- Counts must be **provider-reported only** — never token estimates. A zero-usage run records nothing.
- Ledger writes must never fail the operation that produced them (log + continue).
- Conventional commits with scope, e.g. `feat(usage): …`; end commit messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Work on branch `token-usage-ledger` off `main`.
- Deliberate shortcuts get a `# ponytail:` comment naming the ceiling and upgrade path.
- All backend paths below are relative to `services/`.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `application/dtos/usage_dtos.py` (new) | `TokenUsageEvent`, `KindUsage`, `MemberTokenUsage` | 1 |
| `application/ports/token_usage_store.py` (new) | `TokenUsageStore` Protocol | 1 |
| `infrastructure/read_repositories/mongo_token_usage_store.py` (new) | Mongo adapter + pure doc/reshape helpers | 1 |
| `infrastructure/config.py` | `mongo_token_usage_collection` setting | 1 |
| `infrastructure/di/container.py` | Wire store + inject into use cases | 1, 3, 4, 5 |
| `interfaces/api/main.py` | `ensure_indexes()` at startup | 1 |
| `infrastructure/llm/token_counter.py` | Identity fields + `call_config()` | 2 |
| `infrastructure/llm/adapters/langchain_llm_client.py`, `…/tool_calling_adapter.py` | Use `call_config()` | 2 |
| `application/use_cases/chat_use_cases.py` | Use-case-owned counter, `finally` ledger write; windowed usage use case | 3, 4 |
| `infrastructure/chat/agent.py`, `…/thinking_agent.py` | Drop owned counters + estimate fallback | 3 |
| `application/ports/chat_repository.py`, `infrastructure/chat/mongo_chat_repository.py` | Delete `get_user_token_usage` | 4 |
| `interfaces/api/routes/chat_routes.py` | `days`/`kind` params on `/chat/usage` | 4 |
| `application/services/usage_recording.py` (new) | `ingestion_counter`, `record_ingestion_usage` | 5 |
| `application/use_cases/summarization_use_cases.py`, `…/extract_document_metadata_use_case.py` | Wrap LLM sections | 5 |
| `application/dtos/stats_dtos.py`, `interfaces/api/routes/stats_routes.py` | `MemberUsageStatsResponse` + admin endpoint | 6 |
| `web/apps/portal/src/hooks/use-stats.ts`, `…/lib/query-keys.ts`, `…/app/[workspace]/stats/page.tsx` | Member-usage card | 7 |
| `scripts/backfill_chat_token_usage.py` (new) | One-time idempotent chat backfill | 8 |

---

### Task 1: Token usage ledger — DTOs, port, Mongo adapter, config, DI, startup indexes

**Files:**
- Create: `application/dtos/usage_dtos.py`
- Create: `application/ports/token_usage_store.py`
- Create: `infrastructure/read_repositories/mongo_token_usage_store.py`
- Modify: `infrastructure/config.py` (after `mongo_user_activity_collection`, ~line 76)
- Modify: `infrastructure/di/container.py` (next to the `ChatRepository` wiring, ~line 845)
- Modify: `interfaces/api/main.py` (after the chat `ensure_indexes` block, ~line 90)
- Test: `tests/infrastructure/test_token_usage_store.py` (new)

**Interfaces:**
- Consumes: `TokenUsageDTO` from `application/dtos/chat_dtos.py` (fields `prompt: int`, `completion: int`, `total: int`).
- Produces (later tasks rely on these exact names):
  - `TokenUsageEvent(event_id: str | None, workspace_id: UUID | None, user_id: UUID | None, kind: Literal["chat", "ingestion"], source: str, prompt: int, completion: int, total: int, model: str | None, ref: str | None, created_at: datetime)`
  - `KindUsage(prompt: int, completion: int, total: int, event_count: int)`
  - `MemberTokenUsage(user_id: str | None, chat: KindUsage, ingestion: KindUsage, total_tokens: int)`
  - `TokenUsageStore` Protocol: `record(event)`, `sum_for_user(workspace_id, user_id, *, since=None, kind=None) -> TokenUsageDTO`, `usage_by_member(workspace_id, *, since) -> list[MemberTokenUsage]`, `ensure_indexes()`
  - `MongoTokenUsageStore(client, db_name, collection_name)` implementing the port.

- [ ] **Step 1: Write the failing tests** (pure helpers — the Mongo repos in this codebase have no integration tests; aggregation-pipeline logic lives in pure functions so it *is* testable)

Create `tests/infrastructure/test_token_usage_store.py`:

```python
"""Pure-logic tests for the token usage ledger adapter (doc mapping + reshaping)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from application.dtos.usage_dtos import TokenUsageEvent
from infrastructure.read_repositories.mongo_token_usage_store import (
    _event_to_doc,
    _rows_to_members,
)


def _event(**overrides) -> TokenUsageEvent:
    base = dict(
        workspace_id=uuid4(),
        user_id=uuid4(),
        kind="chat",
        source="chat_message",
        prompt=100,
        completion=20,
        total=120,
        ref="conv-1",
        created_at=datetime(2026, 7, 13, tzinfo=UTC),
    )
    base.update(overrides)
    return TokenUsageEvent(**base)


def test_event_to_doc_stringifies_uuids_and_keeps_counts() -> None:
    ev = _event()
    doc = _event_to_doc(ev)
    assert doc["workspace_id"] == str(ev.workspace_id)
    assert doc["user_id"] == str(ev.user_id)
    assert (doc["prompt"], doc["completion"], doc["total"]) == (100, 20, 120)
    assert doc["kind"] == "chat"
    assert doc["source"] == "chat_message"
    assert "_id" not in doc  # no event_id -> Mongo assigns one


def test_event_to_doc_uses_event_id_as_mongo_id() -> None:
    doc = _event_to_doc(_event(event_id="chat:abc"))
    assert doc["_id"] == "chat:abc"


def test_event_to_doc_allows_unattributed_usage() -> None:
    doc = _event_to_doc(_event(user_id=None, workspace_id=None))
    assert doc["user_id"] is None
    assert doc["workspace_id"] is None


def test_rows_to_members_splits_kinds_and_sorts_by_total() -> None:
    rows = [
        {"_id": {"user_id": "u1", "kind": "chat"}, "prompt": 10, "completion": 5, "total": 15, "events": 2},
        {"_id": {"user_id": "u1", "kind": "ingestion"}, "prompt": 100, "completion": 0, "total": 100, "events": 1},
        {"_id": {"user_id": "u2", "kind": "chat"}, "prompt": 500, "completion": 50, "total": 550, "events": 3},
    ]
    members = _rows_to_members(rows)
    assert [m.user_id for m in members] == ["u2", "u1"]  # sorted by total desc
    u1 = members[1]
    assert u1.chat.total == 15 and u1.chat.event_count == 2
    assert u1.ingestion.total == 100 and u1.ingestion.event_count == 1
    assert u1.total_tokens == 115


def test_rows_to_members_handles_unattributed_row() -> None:
    rows = [{"_id": {"user_id": None, "kind": "ingestion"}, "prompt": 7, "completion": 0, "total": 7, "events": 1}]
    members = _rows_to_members(rows)
    assert members[0].user_id is None
    assert members[0].ingestion.total == 7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services && uv run pytest tests/infrastructure/test_token_usage_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'application.dtos.usage_dtos'`

- [ ] **Step 3: Create the DTOs**

Create `application/dtos/usage_dtos.py`:

```python
"""DTOs for the token usage ledger (chat + ingestion accounting)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class TokenUsageEvent(BaseModel):
    """One append-only ledger entry: real provider-reported tokens for one unit of work.

    ``event_id`` (optional) becomes the Mongo ``_id`` so writers that need
    idempotency (live chat writes, the backfill script) can upsert on a
    deterministic key like ``chat:{message_id}``. Ingestion writers omit it —
    every retry attempt consumed real tokens and must append.
    """

    event_id: str | None = None
    workspace_id: UUID | None = None
    user_id: UUID | None = None
    kind: Literal["chat", "ingestion"]
    source: str  # chat_message | page_summary | artifact_summary | doc_metadata
    prompt: int = 0
    completion: int = 0
    total: int = 0
    model: str | None = None
    ref: str | None = None  # conversation_id / page_id / artifact_id
    created_at: datetime


class KindUsage(BaseModel):
    """Aggregated usage for one (member, kind) cell."""

    prompt: int = 0
    completion: int = 0
    total: int = 0
    event_count: int = 0


class MemberTokenUsage(BaseModel):
    """Per-member usage split by kind, for the admin stats view."""

    user_id: str | None
    chat: KindUsage = KindUsage()
    ingestion: KindUsage = KindUsage()
    total_tokens: int = 0
```

- [ ] **Step 4: Create the port**

Create `application/ports/token_usage_store.py`:

```python
"""Port for the append-only token usage ledger."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from application.dtos.chat_dtos import TokenUsageDTO
from application.dtos.usage_dtos import MemberTokenUsage, TokenUsageEvent


class TokenUsageStore(Protocol):
    """Append-only ledger of LLM token usage, independent of chat CRUD.

    Deleting a conversation must never change recorded usage — that is the
    ledger's reason to exist (quota integrity).
    """

    async def record(self, event: TokenUsageEvent) -> None:
        """Append one usage event (upsert when ``event.event_id`` is set)."""
        ...

    async def sum_for_user(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        since: datetime | None = None,
        kind: str | None = None,
    ) -> TokenUsageDTO:
        """Sum a user's usage, optionally windowed and filtered by kind."""
        ...

    async def usage_by_member(
        self,
        workspace_id: UUID,
        *,
        since: datetime,
    ) -> list[MemberTokenUsage]:
        """Per-member usage in a workspace since ``since``, split by kind."""
        ...

    async def ensure_indexes(self) -> None: ...
```

- [ ] **Step 5: Create the Mongo adapter**

Create `infrastructure/read_repositories/mongo_token_usage_store.py`:

```python
"""MongoDB adapter for the TokenUsageStore port."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import structlog
from motor.motor_asyncio import AsyncIOMotorClient

from application.dtos.chat_dtos import TokenUsageDTO
from application.dtos.usage_dtos import KindUsage, MemberTokenUsage, TokenUsageEvent

log = structlog.get_logger(__name__)


def _event_to_doc(event: TokenUsageEvent) -> dict:
    doc: dict = {
        "workspace_id": str(event.workspace_id) if event.workspace_id else None,
        "user_id": str(event.user_id) if event.user_id else None,
        "kind": event.kind,
        "source": event.source,
        "prompt": event.prompt,
        "completion": event.completion,
        "total": event.total,
        "model": event.model,
        "ref": event.ref,
        "created_at": event.created_at,
    }
    if event.event_id:
        doc["_id"] = event.event_id
    return doc


def _rows_to_members(rows: list[dict]) -> list[MemberTokenUsage]:
    """Reshape $group rows keyed by (user_id, kind) into per-member entries."""
    by_user: dict[str | None, MemberTokenUsage] = {}
    for r in rows:
        user_id = r["_id"]["user_id"]
        kind = r["_id"]["kind"]
        member = by_user.setdefault(user_id, MemberTokenUsage(user_id=user_id))
        cell = KindUsage(
            prompt=int(r.get("prompt", 0)),
            completion=int(r.get("completion", 0)),
            total=int(r.get("total", 0)),
            event_count=int(r.get("events", 0)),
        )
        if kind == "ingestion":
            member.ingestion = cell
        else:
            member.chat = cell
        member.total_tokens = member.chat.total + member.ingestion.total
    return sorted(by_user.values(), key=lambda m: m.total_tokens, reverse=True)


class MongoTokenUsageStore:
    """Append-only ledger of LLM token usage events."""

    def __init__(
        self,
        client: AsyncIOMotorClient,
        db_name: str,
        collection_name: str = "token_usage_events",
    ) -> None:
        self._coll = client[db_name][collection_name]

    async def record(self, event: TokenUsageEvent) -> None:
        doc = _event_to_doc(event)
        if "_id" in doc:
            # Deterministic id (live chat writes + backfill) -> idempotent.
            await self._coll.replace_one({"_id": doc["_id"]}, doc, upsert=True)
        else:
            await self._coll.insert_one(doc)

    async def sum_for_user(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        since: datetime | None = None,
        kind: str | None = None,
    ) -> TokenUsageDTO:
        match: dict = {"workspace_id": str(workspace_id), "user_id": str(user_id)}
        if since is not None:
            match["created_at"] = {"$gte": since}
        if kind is not None:
            match["kind"] = kind
        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": None,
                    "prompt": {"$sum": "$prompt"},
                    "completion": {"$sum": "$completion"},
                    "total": {"$sum": "$total"},
                },
            },
        ]
        docs = await self._coll.aggregate(pipeline).to_list(length=1)
        if not docs:
            return TokenUsageDTO(prompt=0, completion=0, total=0)
        d = docs[0]
        return TokenUsageDTO(
            prompt=int(d.get("prompt", 0)),
            completion=int(d.get("completion", 0)),
            total=int(d.get("total", 0)),
        )

    async def usage_by_member(
        self,
        workspace_id: UUID,
        *,
        since: datetime,
    ) -> list[MemberTokenUsage]:
        pipeline = [
            {"$match": {"workspace_id": str(workspace_id), "created_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": {"user_id": "$user_id", "kind": "$kind"},
                    "prompt": {"$sum": "$prompt"},
                    "completion": {"$sum": "$completion"},
                    "total": {"$sum": "$total"},
                    "events": {"$sum": 1},
                },
            },
        ]
        rows = await self._coll.aggregate(pipeline).to_list(length=1000)
        return _rows_to_members(rows)

    async def ensure_indexes(self) -> None:
        # ponytail: one compound index; workspace-only admin aggregations prefix-scan
        # it. Add (workspace_id, created_at) if member stats get slow at volume.
        await self._coll.create_index(
            [("workspace_id", 1), ("user_id", 1), ("created_at", -1)],
            name="idx_usage_ws_user_time",
        )
        log.info("usage.ledger.indexes_created")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd services && uv run pytest tests/infrastructure/test_token_usage_store.py -q`
Expected: 5 passed

- [ ] **Step 7: Config + DI + startup indexes**

In `infrastructure/config.py`, directly after the `mongo_user_activity_collection` field:

```python
    mongo_token_usage_collection: str = Field(
        default="token_usage_events",
        validation_alias="MONGO_TOKEN_USAGE_COLLECTION",
    )
```

In `infrastructure/di/container.py`, directly after the `container[ChatRepository] = …` block:

```python
    from application.ports.token_usage_store import TokenUsageStore
    from infrastructure.read_repositories.mongo_token_usage_store import MongoTokenUsageStore

    container[TokenUsageStore] = lambda c: MongoTokenUsageStore(
        client=c[AsyncIOMotorClient],
        db_name=settings.mongo_db,
        collection_name=settings.mongo_token_usage_collection,
    )
```

(If `AsyncIOMotorClient` is not already imported at that point in the file, import it the same way the `ChatRepository` block does.)

In `interfaces/api/main.py`, directly after the chat `ensure_indexes` block (`logger.info("mongodb_chat_indexes_initialized")`):

```python
            # Ensure token usage ledger indexes
            from application.ports.token_usage_store import TokenUsageStore

            usage_store = container[TokenUsageStore]
            await usage_store.ensure_indexes()
            logger.info("mongodb_token_usage_indexes_initialized")
```

- [ ] **Step 8: Run the full suite**

Run: `cd services && uv run pytest tests/ -q`
Expected: all green

- [ ] **Step 9: Commit**

```bash
git add services/application/dtos/usage_dtos.py services/application/ports/token_usage_store.py services/infrastructure/read_repositories/mongo_token_usage_store.py services/infrastructure/config.py services/infrastructure/di/container.py services/interfaces/api/main.py services/tests/infrastructure/test_token_usage_store.py
git commit -m "feat(usage): append-only token usage ledger (port, mongo adapter, DI, indexes)"
```

---

### Task 2: Identity-aware TokenCounter + Langfuse trace attribution

**Files:**
- Modify: `infrastructure/llm/token_counter.py`
- Modify: `infrastructure/llm/adapters/langchain_llm_client.py` (`_config`, ~line 97)
- Modify: `infrastructure/llm/adapters/tool_calling_adapter.py` (the two `config = {"callbacks": …}` sites, ~lines 212 and 282)
- Test: `tests/infrastructure/llm/test_token_accounting.py` (extend)

**Interfaces:**
- Consumes: existing `TokenCounter`, `callbacks_for(langfuse_handler)`.
- Produces (Task 3/5 rely on these):
  - `TokenCounter(*, user_id: str | None = None, session_id: str | None = None, workspace_id: str | None = None, tags: list[str] | None = None)` — all keyword-only, all optional; counting behavior unchanged.
  - `call_config(langfuse_handler: object | None = None) -> dict` — the one place that builds a LangChain call config: callbacks + (when an identified counter is active) Langfuse v3 attribution metadata. Verified against installed langfuse 3.14.5: its LangChain `CallbackHandler` reads `langfuse_session_id`, `langfuse_user_id`, `langfuse_tags` from run metadata (`langfuse/langchain/CallbackHandler.py:280-291`); other metadata keys pass through as trace metadata.

- [ ] **Step 1: Write the failing tests** — append to `tests/infrastructure/llm/test_token_accounting.py`:

```python
from infrastructure.llm.token_counter import call_config


def test_call_config_includes_langfuse_metadata_from_active_counter() -> None:
    counter = TokenCounter(
        user_id="u-1", session_id="conv-1", workspace_id="ws-1", tags=["chat"],
    )
    with counter:
        cfg = call_config(None)
    assert cfg["metadata"] == {
        "langfuse_user_id": "u-1",
        "langfuse_session_id": "conv-1",
        "langfuse_tags": ["chat"],
        "workspace_id": "ws-1",
    }


def test_call_config_omits_metadata_without_identity() -> None:
    with TokenCounter():  # anonymous counter (identity-less)
        assert "metadata" not in call_config(None)
    assert "metadata" not in call_config(None)  # no active counter at all


def test_call_config_keeps_token_and_langfuse_handlers() -> None:
    sentinel = object()
    cfg = call_config(sentinel)
    assert sentinel in cfg["callbacks"]
    assert any(isinstance(cb, TokenCountingCallbackHandler) for cb in cfg["callbacks"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services && uv run pytest tests/infrastructure/llm/test_token_accounting.py -q`
Expected: FAIL — `ImportError: cannot import name 'call_config'`

- [ ] **Step 3: Implement**

In `infrastructure/llm/token_counter.py`, replace the `TokenCounter` `__slots__`/`__init__` with:

```python
class TokenCounter:
    """Accumulates prompt/completion token counts across multiple LLM calls.

    Optional identity fields attribute the scope's work: they feed Langfuse
    trace metadata (via ``call_config``) and let the owner of the scope write
    a ledger event afterwards. Identity-less counters behave exactly as before.
    """

    __slots__ = (
        "_token",
        "completion_tokens",
        "prompt_tokens",
        "session_id",
        "tags",
        "total_tokens",
        "user_id",
        "workspace_id",
    )

    def __init__(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        workspace_id: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0
        self._token = None
        self.user_id = user_id
        self.session_id = session_id
        self.workspace_id = workspace_id
        self.tags = tags
```

At the bottom of the file, after `callbacks_for`, add:

```python
def call_config(langfuse_handler: object | None = None) -> dict:
    """LangChain call config: counting+tracing callbacks, plus Langfuse v3
    trace attribution (``langfuse_*`` metadata keys) when the active counter
    carries identity. The single construction point for every adapter."""
    config: dict = {"callbacks": callbacks_for(langfuse_handler)}
    counter = _active_counter.get()
    if counter is None:
        return config
    metadata: dict = {}
    if counter.user_id:
        metadata["langfuse_user_id"] = counter.user_id
    if counter.session_id:
        metadata["langfuse_session_id"] = counter.session_id
    if counter.tags:
        metadata["langfuse_tags"] = list(counter.tags)
    if counter.workspace_id:
        metadata["workspace_id"] = counter.workspace_id
    if metadata:
        config["metadata"] = metadata
    return config
```

In `infrastructure/llm/adapters/langchain_llm_client.py`, change the import and `_config`:

```python
from infrastructure.llm.token_counter import call_config
```

```python
    def _config(self) -> dict:
        # Counting callback is always attached; Langfuse trace attribution
        # comes from the active TokenCounter's identity (chat/ingestion scopes).
        return call_config(self._langfuse_handler)
```

In `infrastructure/llm/adapters/tool_calling_adapter.py`, change the import (`callbacks_for` → `call_config`) and both config sites:

```python
        config = call_config(self._langfuse_handler)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services && uv run pytest tests/infrastructure/llm/ -q`
Expected: all green (new + existing accounting tests)

- [ ] **Step 5: Full suite, then commit**

Run: `cd services && uv run pytest tests/ -q` — green.

```bash
git add services/infrastructure/llm/token_counter.py services/infrastructure/llm/adapters/langchain_llm_client.py services/infrastructure/llm/adapters/tool_calling_adapter.py services/tests/infrastructure/llm/test_token_accounting.py
git commit -m "feat(usage): identity-aware TokenCounter + langfuse user/session trace attribution"
```

---

### Task 3: Chat — use-case-owned counter, ledger write in `finally`, delete the estimate fallback

**Files:**
- Modify: `application/use_cases/chat_use_cases.py` (`SendMessageUseCase`)
- Modify: `infrastructure/chat/agent.py` (counter ownership ~lines 63-78 and 330-348)
- Modify: `infrastructure/chat/thinking_agent.py` (same pattern, ~lines 84-100 and 455-478)
- Modify: `infrastructure/di/container.py` (`SendMessageUseCase` factory, ~line 985)
- Test: `tests/application/test_send_message_usage.py` (new)

**Interfaces:**
- Consumes: `TokenUsageStore.record(TokenUsageEvent)` (Task 1); `TokenCounter(user_id=…, session_id=…, workspace_id=…, tags=…)` and `get_active_counter()` (Task 2).
- Produces: `SendMessageUseCase(chat_repository, chat_agent, token_usage_store)`. Behavior contract: exactly one ledger write per `execute()` run with `counter.total_tokens > 0` — on success, on agent exception, and on consumer close (client disconnect). Agents' `done` event reports provider counts only (no streamed-chunk fallback).

**Semantics being locked in:**
- The `with counter:` in the use case makes the counter ambient for the whole agent pipeline (same contextvar mechanics the agents use today — verified working across `astream`, `asyncio.gather`, and structured/tool paths by the 2026-07-13 runtime harness).
- The ledger write lives in `finally` and is `asyncio.shield`-protected: a client disconnect cancels the generator, but the write still lands. Quota must not be evadable by dropping the connection.
- `event_id = f"chat:{message_id}"` when the done event arrived (idempotent with the Task 8 backfill); partial runs (no done event) insert without an id.
- The per-message `token_usage` field on `chat_messages` keeps being written (existing UI/admin stats read it); the ledger is the accounting source of truth.

- [ ] **Step 1: Write the failing tests**

Create `tests/application/test_send_message_usage.py`:

```python
"""SendMessageUseCase must write exactly one ledger event per run —
including error and client-disconnect paths (holes 2+3 of the audit)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from application.dtos.chat_dtos import AgentEvent, ChatMessageDTO, ConversationDTO
from application.use_cases.chat_use_cases import SendMessageUseCase
from infrastructure.llm.token_counter import record_usage


def _conversation(conversation_id, workspace_id, owner_id) -> ConversationDTO:
    now = datetime.now(UTC)
    return ConversationDTO(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        owner_id=owner_id,
        title="t",
        folder_id=None,
        created_at=now,
        updated_at=now,
        message_count=0,
        model_used=None,
        is_archived=False,
    )


class FakeChatRepo:
    def __init__(self, conversation: ConversationDTO) -> None:
        self._conversation = conversation
        self.messages: list[ChatMessageDTO] = []

    async def get_conversation(self, conversation_id, workspace_id=None):
        return self._conversation

    async def append_message(self, message):
        self.messages.append(message)
        return message

    async def update_conversation(self, conversation_id, **kwargs):
        return True

    async def get_recent_messages(self, conversation_id, limit=10):
        return []


class FakeUsageStore:
    def __init__(self) -> None:
        self.events = []

    async def record(self, event) -> None:
        self.events.append(event)


class FakeAgent:
    """Simulates the LLM pipeline: records usage onto the ambient counter
    (exactly what the real adapters' on_llm_end callback does), then yields."""

    def __init__(self, *, usage=(100, 20), fail=False, hang=False) -> None:
        self._usage = usage
        self._fail = fail
        self._hang = hang
        self.message_id = uuid4()

    async def run(self, **kwargs):
        if self._usage:
            record_usage(*self._usage)
        yield AgentEvent(type="step_started", step="s1", description="d")
        if self._fail:
            raise RuntimeError("pipeline blew up")
        if self._hang:
            yield AgentEvent(type="step_completed", step="s1", status="completed")
            return
        yield AgentEvent(type="token", delta="answer")
        yield AgentEvent(
            type="done",
            message_id=self.message_id,
            total_tokens=120,
            prompt_tokens=100,
            completion_tokens=20,
            duration_ms=5,
        )


def _use_case(agent, store):
    ws, owner, conv = uuid4(), uuid4(), uuid4()
    repo = FakeChatRepo(_conversation(conv, ws, owner))
    uc = SendMessageUseCase(
        chat_repository=repo, chat_agent=agent, token_usage_store=store,
    )
    return uc, repo, ws, owner, conv


@pytest.mark.asyncio
async def test_success_writes_one_attributed_chat_event() -> None:
    store = FakeUsageStore()
    agent = FakeAgent()
    uc, repo, ws, owner, conv = _use_case(agent, store)

    events = [
        e async for e in uc.execute(
            conversation_id=conv, workspace_id=ws, owner_id=owner, message="hi",
        )
    ]

    assert any(e.type == "done" for e in events)
    assert len(store.events) == 1
    ev = store.events[0]
    assert (ev.workspace_id, ev.user_id) == (ws, owner)
    assert (ev.kind, ev.source) == ("chat", "chat_message")
    assert (ev.prompt, ev.completion, ev.total) == (100, 20, 120)
    assert ev.ref == str(conv)
    assert ev.event_id == f"chat:{agent.message_id}"


@pytest.mark.asyncio
async def test_agent_exception_still_records_partial_usage() -> None:
    store = FakeUsageStore()
    uc, repo, ws, owner, conv = _use_case(FakeAgent(fail=True), store)

    with pytest.raises(RuntimeError):
        async for _ in uc.execute(
            conversation_id=conv, workspace_id=ws, owner_id=owner, message="hi",
        ):
            pass

    assert len(store.events) == 1
    assert store.events[0].total == 120
    assert store.events[0].event_id is None  # no done event -> no message id


@pytest.mark.asyncio
async def test_client_disconnect_still_records_usage() -> None:
    store = FakeUsageStore()
    uc, repo, ws, owner, conv = _use_case(FakeAgent(hang=True), store)

    gen = uc.execute(conversation_id=conv, workspace_id=ws, owner_id=owner, message="hi")
    await gen.__anext__()  # consume one event, then the client goes away
    await gen.aclose()

    assert len(store.events) == 1
    assert store.events[0].total == 120


@pytest.mark.asyncio
async def test_zero_usage_records_nothing() -> None:
    store = FakeUsageStore()
    uc, repo, ws, owner, conv = _use_case(FakeAgent(usage=None), store)

    async for _ in uc.execute(
        conversation_id=conv, workspace_id=ws, owner_id=owner, message="hi",
    ):
        pass

    assert store.events == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services && uv run pytest tests/application/test_send_message_usage.py -q`
Expected: FAIL — `TypeError: SendMessageUseCase.__init__() got an unexpected keyword argument 'token_usage_store'`

- [ ] **Step 3: Implement `SendMessageUseCase` changes** in `application/use_cases/chat_use_cases.py`

Add imports at the top of the file:

```python
import asyncio

from application.dtos.usage_dtos import TokenUsageEvent
from application.ports.token_usage_store import TokenUsageStore
from infrastructure.llm.token_counter import TokenCounter
```

Change the constructor:

```python
    def __init__(
        self,
        chat_repository: ChatRepository,
        chat_agent: ChatAgentPort,
        token_usage_store: TokenUsageStore,
    ) -> None:
        self._repo = chat_repository
        self._agent = chat_agent
        self._usage = token_usage_store
```

In `execute()`, wrap the agent loop and the post-loop persistence in a counter + inner `try/finally`. The block currently starting at `# Run agent pipeline and stream events, accumulating step trace` (local accumulators, then `async for event in self._agent.run(…)`) becomes:

```python
            # Run agent pipeline and stream events, accumulating step trace
            draft_answer = ""
            final_sources: list = []
            final_event: AgentEvent | None = None
            trace_steps: dict[str, AgentStepDTO] = {}
            thinking_blocks: list[ThinkingBlockDTO] = []
            grounding_is_grounded: bool | None = None
            grounding_confidence: float | None = None
            query_context: QueryContextDTO | None = None
            structured_blocks: list[ContentBlockDTO] = []
            reasoning_parts: list[str] = []

            # The counter is ambient for the whole pipeline: every LLM call the
            # agent makes (planning, tool loop, synthesis, formatting) records
            # provider-reported usage here, and Langfuse traces inherit the
            # user/conversation identity.
            counter = TokenCounter(
                user_id=str(owner_id),
                session_id=str(conversation_id),
                workspace_id=str(workspace_id),
                tags=["chat"],
            )
            try:
                with counter:
                    async for event in self._agent.run(
                        message=message,
                        conversation_history=history,
                        workspace_id=workspace_id,
                        allowed_artifact_ids=allowed_artifact_ids,
                        mode=mode,
                        previous_citations=previous_citations,
                    ):
                        # … existing event-accumulation body, unchanged, through `yield event` …

                # … existing post-loop code, unchanged: query_context grounded flag,
                #     title update, assistant message persistence …
            finally:
                await self._record_chat_usage(
                    counter, workspace_id, owner_id, conversation_id, final_event,
                )
```

(The pre-existing outer `try … finally: reasoning_context.reset_reasoning_override(_reasoning_token)` stays exactly where it is; this new `try/finally` nests inside it. Only indentation of the existing loop/post-loop body changes.)

Add the helper method to `SendMessageUseCase`:

```python
    async def _record_chat_usage(
        self,
        counter: TokenCounter,
        workspace_id: UUID,
        owner_id: UUID,
        conversation_id: UUID,
        final_event: AgentEvent | None,
    ) -> None:
        """Single write point for chat token accounting.

        Runs in ``finally`` so errors and client disconnects still record.
        Shielded: a disconnect cancels this generator mid-write, but the
        ledger write must land — quota must not be evadable by hanging up.
        """
        if counter.total_tokens <= 0:
            return
        message_id = final_event.message_id if final_event else None
        event = TokenUsageEvent(
            event_id=f"chat:{message_id}" if message_id else None,
            workspace_id=workspace_id,
            user_id=owner_id,
            kind="chat",
            source="chat_message",
            prompt=counter.prompt_tokens,
            completion=counter.completion_tokens,
            total=counter.total_tokens,
            ref=str(conversation_id),
            created_at=datetime.now(UTC),
        )
        try:
            await asyncio.shield(self._usage.record(event))
        except asyncio.CancelledError:
            pass  # our await was cancelled; the shielded write completes anyway
        except Exception:
            log.exception(
                "chat.usage.record_failed", conversation_id=str(conversation_id),
            )
```

- [ ] **Step 4: Remove agent-owned counters and the estimate fallback**

In `infrastructure/chat/agent.py`:
- Change the import to `from infrastructure.llm.token_counter import get_active_counter` (drop `TokenCounter`).
- Delete `token_counter = TokenCounter()` and `token_counter.__enter__()`; dedent is NOT needed (they're statements, not a block).
- Delete the `finally:` clause whose only statement is `token_counter.__exit__(None, None, None)` (keep the `except Exception` error-event clause).
- Replace the done-event block:

```python
            # Provider-reported counts only (no streamed-chunk estimates); the
            # ambient counter is owned by SendMessageUseCase.
            counter = get_active_counter()
            yield AgentEvent(
                type="done",
                message_id=message_id,
                total_tokens=counter.total_tokens if counter else 0,
                duration_ms=elapsed_ms,
                sources=used_citations,
                prompt_tokens=counter.prompt_tokens if counter else 0,
                completion_tokens=counter.completion_tokens if counter else 0,
            )
```

- Keep the local `total_tokens` chunk tally only where it feeds `tokens_streamed=` log/step fields; it no longer reaches the done event.

Apply the identical edit to `infrastructure/chat/thinking_agent.py` (its done-event block carries the same fields plus its own `sources=used_citations`; the `# Use real API token counts if available, fall back to streamed count` comment gets deleted). `thinking_agent_v1.py` is untouched (unrouted legacy; it now gets counted for free via the ambient counter if ever revived).

- [ ] **Step 5: Wire DI** — in `infrastructure/di/container.py`:

```python
    container[SendMessageUseCase] = lambda c: SendMessageUseCase(
        chat_repository=c[ChatRepository],
        chat_agent=c[ChatAgentPort],
        token_usage_store=c[TokenUsageStore],
    )
```

- [ ] **Step 6: Run the new tests, then verify the fallback is gone**

Run: `cd services && uv run pytest tests/application/test_send_message_usage.py -q`
Expected: 4 passed

Run: `grep -rn "else total_tokens" infrastructure/chat/agent.py infrastructure/chat/thinking_agent.py`
Expected: no matches

- [ ] **Step 7: Full suite** — `cd services && uv run pytest tests/ -q`. Fix any test constructing `SendMessageUseCase` without the new argument (search: `grep -rln "SendMessageUseCase(" tests/`) by passing a `FakeUsageStore` like the one above.

- [ ] **Step 8: Commit**

```bash
git add services/application/use_cases/chat_use_cases.py services/infrastructure/chat/agent.py services/infrastructure/chat/thinking_agent.py services/infrastructure/di/container.py services/tests/application/test_send_message_usage.py
git commit -m "feat(usage): use-case-owned counter + disconnect-proof chat ledger writes; drop chunk-count estimate"
```

---

### Task 4: Windowed per-user usage from the ledger (badge + quota-ready reads)

**Files:**
- Modify: `application/use_cases/chat_use_cases.py` (`GetUserTokenUsageUseCase`, ~line 188)
- Modify: `application/ports/chat_repository.py` (delete `get_user_token_usage`, ~line 52)
- Modify: `infrastructure/chat/mongo_chat_repository.py` (delete `get_user_token_usage`, lines ~115-152)
- Modify: `interfaces/api/routes/chat_routes.py` (`GET /chat/usage`, ~line 123)
- Modify: `infrastructure/di/container.py` (`GetUserTokenUsageUseCase` factory, ~line 979)
- Test: `tests/application/test_chat_usage_use_case.py` (rewrite fakes)

**Interfaces:**
- Consumes: `TokenUsageStore.sum_for_user(workspace_id, user_id, *, since, kind)` (Task 1).
- Produces: `GetUserTokenUsageUseCase(token_usage_store).execute(workspace_id, owner_id, days: int | None = None, kind: str | None = None) -> Result[TokenUsageDTO, AppError]`. Route: `GET /chat/usage?days=&kind=`.
- **Semantic change (intended):** the badge total now (a) survives conversation deletion, and (b) includes ingestion usage when `kind` is omitted — it reports the user's full token footprint. The FE badge needs no change (same `TokenUsageDTO` shape).

- [ ] **Step 1: Rewrite the failing tests** — replace the body of `tests/application/test_chat_usage_use_case.py`:

```python
"""GetUserTokenUsageUseCase — per-user token totals from the usage ledger."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from returns.result import Failure, Success

from application.dtos.chat_dtos import TokenUsageDTO
from application.use_cases.chat_use_cases import GetUserTokenUsageUseCase


class _FakeUsageStore:
    def __init__(self, usage: TokenUsageDTO | None = None, *, raises: bool = False) -> None:
        self._usage = usage or TokenUsageDTO()
        self._raises = raises
        self.calls: list[dict] = []

    async def sum_for_user(self, workspace_id, user_id, *, since=None, kind=None):
        self.calls.append(
            {"workspace_id": workspace_id, "user_id": user_id, "since": since, "kind": kind},
        )
        if self._raises:
            raise RuntimeError("boom")
        return self._usage


@pytest.mark.asyncio
async def test_returns_all_time_usage_by_default() -> None:
    usage = TokenUsageDTO(prompt=1000, completion=200, total=1200)
    store = _FakeUsageStore(usage=usage)
    ws, owner = uuid4(), uuid4()

    result = await GetUserTokenUsageUseCase(token_usage_store=store).execute(
        workspace_id=ws, owner_id=owner,
    )

    assert isinstance(result, Success)
    assert result.unwrap() == usage
    assert store.calls == [{"workspace_id": ws, "user_id": owner, "since": None, "kind": None}]


@pytest.mark.asyncio
async def test_days_window_translates_to_since() -> None:
    store = _FakeUsageStore()
    await GetUserTokenUsageUseCase(token_usage_store=store).execute(
        workspace_id=uuid4(), owner_id=uuid4(), days=30, kind="chat",
    )
    call = store.calls[0]
    assert call["kind"] == "chat"
    expected = datetime.now(UTC) - timedelta(days=30)
    assert abs((call["since"] - expected).total_seconds()) < 5


@pytest.mark.asyncio
async def test_store_error_maps_to_failure() -> None:
    store = _FakeUsageStore(raises=True)
    result = await GetUserTokenUsageUseCase(token_usage_store=store).execute(
        workspace_id=uuid4(), owner_id=uuid4(),
    )
    assert isinstance(result, Failure)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services && uv run pytest tests/application/test_chat_usage_use_case.py -q`
Expected: FAIL — unexpected keyword argument `token_usage_store`

- [ ] **Step 3: Implement**

Replace `GetUserTokenUsageUseCase` in `application/use_cases/chat_use_cases.py`:

```python
class GetUserTokenUsageUseCase:
    """Per-user token totals from the usage ledger (optionally windowed)."""

    def __init__(self, token_usage_store: TokenUsageStore) -> None:
        self._usage = token_usage_store

    async def execute(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        days: int | None = None,
        kind: str | None = None,
    ) -> Result[TokenUsageDTO, AppError]:
        try:
            since = datetime.now(UTC) - timedelta(days=days) if days else None
            usage = await self._usage.sum_for_user(
                workspace_id, owner_id, since=since, kind=kind,
            )
            return Success(usage)
        except Exception as e:
            log.exception("chat.usage.get_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to get token usage: {e!s}"))
```

(Add `from datetime import timedelta` to the file's datetime import if not present.)

Delete `get_user_token_usage` from `application/ports/chat_repository.py` (the whole method, ~line 52) and from `infrastructure/chat/mongo_chat_repository.py` (lines ~115-152, including its `# ponytail:` comment — the ledger *is* the upgrade that comment named).

Update the route in `interfaces/api/routes/chat_routes.py`:

```python
@router.get("/usage", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def get_user_token_usage(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
    kind: Annotated[str | None, Query(pattern="^(chat|ingestion)$")] = None,
) -> TokenUsageDTO:
    """Current user's token usage from the ledger (all-time unless ``days`` given)."""
    use_case = container[GetUserTokenUsageUseCase]
    return await use_case.execute(
        workspace_id=auth.workspace_id,
        owner_id=auth.user_id,
        days=days,
        kind=kind,
    )
```

(Add `Query` to the fastapi import in that file if missing.)

Update DI in `infrastructure/di/container.py`:

```python
    container[GetUserTokenUsageUseCase] = lambda c: GetUserTokenUsageUseCase(
        token_usage_store=c[TokenUsageStore],
    )
```

- [ ] **Step 4: Run tests, full suite**

Run: `cd services && uv run pytest tests/application/test_chat_usage_use_case.py -q` — 3 passed.
Run: `cd services && uv run pytest tests/ -q` — green (nothing else referenced the deleted repo method; verify with `grep -rn "get_user_token_usage" --include='*.py' . | grep -v token_usage_store` → only use case + route remain).

- [ ] **Step 5: Commit**

```bash
git add services/application/use_cases/chat_use_cases.py services/application/ports/chat_repository.py services/infrastructure/chat/mongo_chat_repository.py services/interfaces/api/routes/chat_routes.py services/infrastructure/di/container.py services/tests/application/test_chat_usage_use_case.py
git commit -m "feat(usage): per-user usage reads from ledger with optional window/kind; drop \$lookup aggregate"
```

---

### Task 5: Ingestion capture — page summary, artifact summary, doc-metadata fallback

**Files:**
- Create: `application/services/usage_recording.py`
- Modify: `application/use_cases/summarization_use_cases.py` (both use cases)
- Modify: `application/use_cases/extract_document_metadata_use_case.py` (`__init__` + the `_llm_extract` call site at ~line 323)
- Modify: `infrastructure/di/container.py` (three factories, ~lines 558, 646, 659)
- Modify: `tests/mocks.py` (`MockLLMClient`, ~line 435)
- Test: `tests/application/test_ingestion_usage_recording.py` (new)

**Interfaces:**
- Consumes: `TokenUsageStore.record`, `TokenUsageEvent` (Task 1); `TokenCounter` identity kwargs (Task 2). The `Artifact` aggregate already carries `workspace_id`/`owner_id` (`domain/aggregates/artifact.py:90-91`) and is already loaded in all three use cases — **no Temporal workflow/activity/event signature changes are needed.**
- Produces:
  - `ingestion_counter(artifact, *, source: str) -> TokenCounter`
  - `record_ingestion_usage(store, counter, *, artifact, source: str, ref: str, model: str | None = None) -> None` — no-op when `store is None` or zero usage; never raises.
  - The three use cases accept `token_usage_store: TokenUsageStore | None = None` (keyword, defaulted, so existing constructions keep working).
- **Retry semantics (intended):** ingestion events have no `event_id`. A Temporal retry re-runs the LLM calls and appends another event — each attempt consumed real tokens, so appending is the honest count. Partial usage from a failed attempt is recorded by the `finally`.

- [ ] **Step 1: Extend `MockLLMClient`** so tests can simulate provider-reported usage (mirrors what the real adapters' `on_llm_end` callback does). In `tests/mocks.py`, add a `usage` parameter:

```python
class MockLLMClient:
    """Mock implementation of LLMClientPort."""

    def __init__(
        self,
        response: str = "Mock summary text.",
        raise_on_call: Exception | None = None,
        usage: tuple[int, int] | None = None,
    ) -> None:
        self._response = response
        self.raise_on_call = raise_on_call
        self._usage = usage
        self.complete_calls: list[str] = []
        self.complete_with_image_calls: list[tuple[str, str]] = []

    def _record(self) -> None:
        if self._usage:
            from infrastructure.llm.token_counter import record_usage

            record_usage(*self._usage)
```

and call `self._record()` as the first statement (before the `raise_on_call` check? **No** — after it, matching real behavior only when a response is produced… actually a failed HTTP call reports no usage, so): add `self._record()` immediately *before* each `return self._response` / structured return in `complete`, `complete_with_image`, and `complete_structured`.

- [ ] **Step 2: Write the failing tests**

Create `tests/application/test_ingestion_usage_recording.py`:

```python
"""Ingestion-side token accounting: enrichment LLM calls must land on the ledger,
attributed to the uploading user via the Artifact aggregate."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from returns.result import Failure, Success

from application.use_cases.summarization_use_cases import SummarizePageUseCase
from domain.aggregates.artifact import Artifact
from domain.aggregates.page import Page
from domain.value_objects.artifact_type import ArtifactType
from domain.value_objects.mime_type import MimeType
from domain.value_objects.text_mention import TextMention
from tests.mocks import (
    MockArtifactRepository,
    MockBlobStore,
    MockLLMClient,
    MockPageRepository,
    MockPromptRepository,
)

_LONG_TEXT = "A" * 101


class FakeUsageStore:
    def __init__(self) -> None:
        self.events = []

    async def record(self, event) -> None:
        self.events.append(event)


def _setup(owner_id: UUID, workspace_id: UUID, *, usage=(300, 40)):
    artifact = Artifact.create(
        source_uri=None,
        source_filename="slides.pdf",
        artifact_type=ArtifactType.RESEARCH_ARTICLE,
        mime_type=MimeType.PDF,
        storage_location="/storage/slides.pdf",
        workspace_id=workspace_id,
        owner_id=owner_id,
    )
    page = Page.create(name="Slide 1", artifact_id=artifact.id, index=0)
    page.update_text_mention(TextMention(text=_LONG_TEXT))

    artifact_repo = MockArtifactRepository()
    artifact_repo.artifacts[artifact.id] = artifact
    page_repo = MockPageRepository()
    page_repo.pages[page.id] = page

    store = FakeUsageStore()
    use_case = SummarizePageUseCase(
        page_repository=page_repo,
        artifact_repository=artifact_repo,
        llm_client=MockLLMClient(response="Summary.", usage=usage),
        prompt_repository=MockPromptRepository(),
        blob_store=MockBlobStore(exists_result=True, bytes_result=b"png-bytes"),
        external_event_publisher=None,
        token_usage_store=store,
    )
    return use_case, page, artifact, store


@pytest.mark.asyncio
async def test_page_summary_records_attributed_ingestion_event() -> None:
    owner, ws = uuid4(), uuid4()
    use_case, page, artifact, store = _setup(owner, ws)

    result = await use_case.execute(page.id)

    assert isinstance(result, Success)
    assert len(store.events) == 1
    ev = store.events[0]
    assert (ev.kind, ev.source) == ("ingestion", "page_summary")
    assert (ev.user_id, ev.workspace_id) == (owner, ws)
    assert (ev.prompt, ev.completion, ev.total) == (300, 40, 340)
    assert ev.ref == str(page.id)
    assert ev.event_id is None  # retries append, never dedupe


@pytest.mark.asyncio
async def test_zero_usage_records_nothing() -> None:
    use_case, page, artifact, store = _setup(uuid4(), uuid4(), usage=None)
    result = await use_case.execute(page.id)
    assert isinstance(result, Success)
    assert store.events == []


@pytest.mark.asyncio
async def test_no_store_is_a_harmless_noop() -> None:
    owner, ws = uuid4(), uuid4()
    use_case, page, artifact, store = _setup(owner, ws)
    use_case.token_usage_store = None
    result = await use_case.execute(page.id)
    assert isinstance(result, Success)


@pytest.mark.asyncio
async def test_llm_failure_after_usage_still_records_partial() -> None:
    """A run that dies after the provider reported usage (e.g. a later call in
    a multi-call chain fails) must still land its partial spend on the ledger."""
    owner, ws = uuid4(), uuid4()
    use_case, page, artifact, store = _setup(owner, ws)

    class _RecordThenFailLLM(MockLLMClient):
        async def complete_with_image(self, prompt: str, image_b64: str, **kwargs):
            self._record()  # provider reported usage…
            raise RuntimeError("…then the run died")

    use_case.llm_client = _RecordThenFailLLM(usage=(50, 0))

    result = await use_case.execute(page.id)

    assert isinstance(result, Failure)  # use case maps the error as before
    assert len(store.events) == 1  # …but the spend was recorded by the finally
    assert (store.events[0].prompt, store.events[0].total) == (50, 50)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd services && uv run pytest tests/application/test_ingestion_usage_recording.py -q`
Expected: FAIL — unexpected keyword argument `token_usage_store`

- [ ] **Step 4: Create the shared helper**

Create `application/services/usage_recording.py`:

```python
"""Ingestion-side token usage recording (page/artifact summaries, doc metadata).

The Artifact aggregate is already loaded at every enrichment LLM call site and
carries workspace_id/owner_id — so attribution needs no Temporal or event
schema changes. NER (structflo-ner → langextract) is deliberately NOT counted:
it bypasses the LLM client layer and exposes no usage in its return type.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from application.dtos.usage_dtos import TokenUsageEvent
from infrastructure.llm.token_counter import TokenCounter

if TYPE_CHECKING:
    from application.ports.token_usage_store import TokenUsageStore
    from domain.aggregates.artifact import Artifact

log = structlog.get_logger(__name__)


def ingestion_counter(artifact: Artifact, *, source: str) -> TokenCounter:
    """Counter carrying the uploader's identity, for Langfuse + the ledger."""
    return TokenCounter(
        user_id=str(artifact.owner_id) if artifact.owner_id else None,
        session_id=str(artifact.id),
        workspace_id=str(artifact.workspace_id) if artifact.workspace_id else None,
        tags=["ingestion", source],
    )


async def record_ingestion_usage(
    store: TokenUsageStore | None,
    counter: TokenCounter,
    *,
    artifact: Artifact,
    source: str,
    ref: str,
    model: str | None = None,
) -> None:
    """Append one ledger event for an enrichment run. Never raises — a ledger
    hiccup must not fail the pipeline. No event_id: Temporal retries consumed
    real tokens, so every attempt appends."""
    if store is None or counter.total_tokens <= 0:
        return
    try:
        await store.record(
            TokenUsageEvent(
                workspace_id=artifact.workspace_id,
                user_id=artifact.owner_id,
                kind="ingestion",
                source=source,
                prompt=counter.prompt_tokens,
                completion=counter.completion_tokens,
                total=counter.total_tokens,
                model=model,
                ref=ref,
                created_at=datetime.now(UTC),
            ),
        )
    except Exception:
        log.exception("ingestion.usage.record_failed", source=source, ref=ref)
```

- [ ] **Step 5: Wrap the three use cases**

`application/use_cases/summarization_use_cases.py` — add imports:

```python
from application.services.usage_recording import ingestion_counter, record_ingestion_usage
```

**`SummarizePageUseCase`:** add the constructor param (and assignment) `token_usage_store: TokenUsageStore | None = None` (import the port under `TYPE_CHECKING` or directly, matching the file's style). In `execute`, first hoist the model-name lines that currently sit *after* the LLM branch to just *before* it (they're call-order independent):

```python
            model_info = await self.llm_client.get_model_info()
            model_name = (
                f"{model_info.get('provider', 'unknown')}/{model_info.get('model_name', 'unknown')}"
            )
```

then wrap the entire mode/LLM branch (from `if len(slide_text) >= _TEXT_THRESHOLD:` through the `text_only` `summary_text = await self.llm_client.complete(rendered)`) as:

```python
            counter = ingestion_counter(artifact, source="page_summary")
            try:
                with counter:
                    # … existing mode/LLM branch, unchanged, one indent deeper …
            finally:
                await record_ingestion_usage(
                    self.token_usage_store,
                    counter,
                    artifact=artifact,
                    source="page_summary",
                    ref=str(page_id),
                    model=model_name,
                )
```

(Delete the now-duplicated `model_info`/`model_name` lines at their old position after the branch.)

**`SummarizeArtifactUseCase`:** same constructor param. Hoist the same two `model_info`/`model_name` lines above the sliding-window chain, then wrap the chain (from `if len(page_summaries) <= self.batch_size:` through `final_summary = await self._refine(combined, artifact_title)`):

```python
            counter = ingestion_counter(artifact, source="artifact_summary")
            try:
                with counter:
                    # … existing sliding-window chain, unchanged, one indent deeper …
            finally:
                await record_ingestion_usage(
                    self.token_usage_store,
                    counter,
                    artifact=artifact,
                    source="artifact_summary",
                    ref=str(artifact_id),
                    model=model_name,
                )
```

**`ExtractDocumentMetadataUseCase`** (`application/use_cases/extract_document_metadata_use_case.py`): same constructor param + imports. At the single `_llm_extract` call site (~line 323, `llm_result = await self._llm_extract(text)`; `artifact` is in scope from ~line 125):

```python
                counter = ingestion_counter(artifact, source="doc_metadata")
                try:
                    with counter:
                        llm_result = await self._llm_extract(text)
                finally:
                    await record_ingestion_usage(
                        self.token_usage_store,
                        counter,
                        artifact=artifact,
                        source="doc_metadata",
                        ref=str(artifact_id),
                    )
```

- [ ] **Step 6: Wire DI** — in `infrastructure/di/container.py`, add `token_usage_store=c[TokenUsageStore],` to the `SummarizePageUseCase`, `SummarizeArtifactUseCase`, and `ExtractDocumentMetadataUseCase` factories.

- [ ] **Step 7: Run tests, full suite**

Run: `cd services && uv run pytest tests/application/test_ingestion_usage_recording.py tests/application/test_summarization_use_cases.py tests/application/test_extract_document_metadata.py -q`
Expected: all pass (existing tests unaffected — the new param defaults to `None`).

Run: `cd services && uv run pytest tests/ -q` — green.

- [ ] **Step 8: Commit**

```bash
git add services/application/services/usage_recording.py services/application/use_cases/summarization_use_cases.py services/application/use_cases/extract_document_metadata_use_case.py services/infrastructure/di/container.py services/tests/mocks.py services/tests/application/test_ingestion_usage_recording.py
git commit -m "feat(usage): record ingestion LLM usage (page/artifact summary, doc metadata) attributed to uploader"
```

---

### Task 6: Admin per-member usage endpoint

**Files:**
- Modify: `application/dtos/stats_dtos.py`
- Modify: `interfaces/api/routes/stats_routes.py` (after `GET /token-usage`, ~line 347)
- Test: `tests/interfaces/test_stats_member_usage.py` (new; mirrors the `FakeContainer` + dependency-override pattern of `tests/interfaces/test_api_routes.py`)

**Interfaces:**
- Consumes: `TokenUsageStore.usage_by_member(workspace_id, *, since)` → `list[MemberTokenUsage]` (Task 1).
- Produces: `GET /stats/member-usage?period=day|week|month` (admin-only, default `month`) → `MemberUsageStatsResponse(members: list[MemberTokenUsage], period_days: int)`.

- [ ] **Step 1: Write the failing test**

Create `tests/interfaces/test_stats_member_usage.py`:

```python
"""GET /stats/member-usage — admin-gated per-member token usage."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from application.dtos.usage_dtos import KindUsage, MemberTokenUsage
from application.ports.token_usage_store import TokenUsageStore
from interfaces.api.main import app
from interfaces.dependencies import get_auth, get_container
from tests.fakes.fake_auth import FakeAuth


class FakeContainer:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]


class FakeUsageStore:
    async def usage_by_member(self, workspace_id, *, since: datetime):
        return [
            MemberTokenUsage(
                user_id="u1",
                chat=KindUsage(prompt=10, completion=2, total=12, event_count=1),
                ingestion=KindUsage(prompt=100, completion=0, total=100, event_count=3),
                total_tokens=112,
            ),
        ]


def _client(*, is_admin: bool) -> TestClient:
    app.dependency_overrides[get_container] = lambda: FakeContainer(
        {TokenUsageStore: FakeUsageStore()},
    )
    app.dependency_overrides[get_auth] = lambda: FakeAuth(
        user_id=uuid4(), workspace_id=uuid4(), is_admin=is_admin,
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
```

Before running: open `tests/fakes/fake_auth.py` and match `FakeAuth`'s actual constructor (it already exists and is used by `tests/interfaces/test_api_routes.py`); adjust the two constructor calls if its signature differs (e.g., role-based instead of `is_admin=`) — the assertion contract stays the same.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services && uv run pytest tests/interfaces/test_stats_member_usage.py -q`
Expected: FAIL — 404 (route doesn't exist)

- [ ] **Step 3: Implement**

In `application/dtos/stats_dtos.py`, add at the end:

```python
# --- Per-member token usage (admin) ---

from application.dtos.usage_dtos import MemberTokenUsage  # noqa: E402


class MemberUsageStatsResponse(BaseModel):
    members: list[MemberTokenUsage]
    period_days: int
```

(If the file's lint setup rejects a late import, move it to the top import block instead — either is fine, keep ruff happy.)

In `interfaces/api/routes/stats_routes.py`, after the `get_token_usage_stats` endpoint:

```python
@router.get("/member-usage", status_code=status.HTTP_200_OK)
async def get_member_usage_stats(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    period: str = Query("month", pattern="^(day|week|month)$"),
) -> MemberUsageStatsResponse:
    """Per-member token usage from the ledger, chat vs ingestion (admin only)."""
    if not auth.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    from application.ports.token_usage_store import TokenUsageStore

    store = container[TokenUsageStore]
    days = _period_to_days(period)
    since = datetime.now(UTC) - timedelta(days=days)
    members = await store.usage_by_member(auth.workspace_id, since=since)
    return MemberUsageStatsResponse(members=members, period_days=days)
```

Add the needed imports at the top of the file (`MemberUsageStatsResponse` from stats_dtos; `datetime`/`UTC`/`timedelta` if not present — check the file's existing imports first).

- [ ] **Step 4: Run tests, full suite**

Run: `cd services && uv run pytest tests/interfaces/test_stats_member_usage.py -q` — 2 passed.
Run: `cd services && uv run pytest tests/ -q` — green.

- [ ] **Step 5: Commit**

```bash
git add services/application/dtos/stats_dtos.py services/interfaces/api/routes/stats_routes.py services/tests/interfaces/test_stats_member_usage.py
git commit -m "feat(usage): admin per-member token usage endpoint (chat vs ingestion split)"
```

---

### Task 7: Frontend — member usage card on the admin stats page

**Files:**
- Modify: `web/apps/portal/src/lib/query-keys.ts` (stats section, ~line 66)
- Modify: `web/apps/portal/src/hooks/use-stats.ts`
- Modify: `web/apps/portal/src/app/[workspace]/stats/page.tsx` (new card after the "Token Usage (daily)" card, ~line 725)

**Interfaces:**
- Consumes: `GET /stats/member-usage?period=` (Task 6); `GET /workspace/members?limit=50` (existing Duar proxy, `services/interfaces/api/routes/workspace_routes.py:13-23`, returns `list[dict]` of member records).
- Produces: `useMemberUsageStats(period)`, `useWorkspaceMembers()` hooks; a "Token Usage by Member" card visible to admins.

- [ ] **Step 1: Query keys** — in `web/apps/portal/src/lib/query-keys.ts` add inside `stats`:

```ts
    memberUsage: (period: string) => [...queryKeys.stats.all, "member-usage", period] as const,
```

- [ ] **Step 2: Hooks** — in `web/apps/portal/src/hooks/use-stats.ts`, add next to the other analytics hooks:

```ts
interface MemberKindUsage {
  prompt: number;
  completion: number;
  total: number;
  event_count: number;
}

export interface MemberTokenUsage {
  user_id: string | null;
  chat: MemberKindUsage;
  ingestion: MemberKindUsage;
  total_tokens: number;
}

interface MemberUsageStatsResponse {
  members: MemberTokenUsage[];
  period_days: number;
}

export function useMemberUsageStats(period = "month") {
  return useQuery({
    queryKey: queryKeys.stats.memberUsage(period),
    queryFn: () =>
      authFetchJson<MemberUsageStatsResponse>(`/stats/member-usage?period=${period}`),
    refetchInterval: 60_000,
  });
}

interface WorkspaceMember {
  user_id?: string;
  id?: string;
  name?: string;
  email?: string;
}

export function useWorkspaceMembers() {
  return useQuery({
    queryKey: ["workspace", "members"],
    queryFn: () => authFetchJson<WorkspaceMember[]>(`/workspace/members?limit=50`),
    staleTime: 300_000,
  });
}
```

(Verify the Duar member record's id field at implementation time — the card below falls back across `user_id` → `id`, and to the raw ledger id when no member matches, so an unexpected shape degrades gracefully, never breaks.)

- [ ] **Step 3: Card** — in `web/apps/portal/src/app/[workspace]/stats/page.tsx`, import the two hooks, call them alongside the other stats hooks (`const memberUsage = useMemberUsageStats(period);` `const members = useWorkspaceMembers();` — reuse the page's existing `period` state), and render after the "Token Usage (daily)" card:

```tsx
        {/* Token usage by member (admin, from the usage ledger) */}
        <Card className="lg:col-span-3">
          <CardHeader title="Token Usage by Member" />
          {!memberUsage.data || memberUsage.data.members.length === 0 ? (
            <p className="py-8 text-center text-sm text-text-muted">
              No recorded usage in this period.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-default text-left text-xs text-text-muted">
                    <th className="py-2 pr-4 font-medium">Member</th>
                    <th className="py-2 pr-4 text-right font-medium">Chat</th>
                    <th className="py-2 pr-4 text-right font-medium">Uploads</th>
                    <th className="py-2 text-right font-medium">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {memberUsage.data.members.map((m) => {
                    const member = (members.data ?? []).find(
                      (wm) => (wm.user_id ?? wm.id) === m.user_id,
                    );
                    const label =
                      member?.name ?? member?.email ?? m.user_id ?? "Unattributed";
                    return (
                      <tr key={m.user_id ?? "unattributed"} className="border-b border-border-default/50">
                        <td className="py-2 pr-4">{label}</td>
                        <td className="py-2 pr-4 text-right tabular-nums">{fmtNumber(m.chat.total)}</td>
                        <td className="py-2 pr-4 text-right tabular-nums">{fmtNumber(m.ingestion.total)}</td>
                        <td className="py-2 text-right font-medium tabular-nums">{fmtNumber(m.total_tokens)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
```

(Match the page's actual `Card`/`CardHeader` props — the existing "Token Usage (daily)" card at ~line 681 is the template; if it uses `padding={false}` + an inner `p-5` div, mirror that. `fmtNumber` already exists in the file.)

- [ ] **Step 4: Verify**

Run: `cd web && pnpm --filter portal lint && pnpm --filter portal build`
Expected: clean (use the repo's actual script names — check `web/apps/portal/package.json` if either script is missing).

- [ ] **Step 5: Commit**

```bash
git add web/apps/portal/src/lib/query-keys.ts web/apps/portal/src/hooks/use-stats.ts "web/apps/portal/src/app/[workspace]/stats/page.tsx"
git commit -m "feat(web): admin member token-usage card (chat vs uploads, from usage ledger)"
```

---

### Task 8: Backfill script — existing chat usage into the ledger

**Files:**
- Create: `scripts/backfill_chat_token_usage.py`

**Interfaces:**
- Consumes: `conversations` (`workspace_id`, `owner_id`) and `chat_messages` (`token_usage`) collections; `settings.mongo_uri`, `settings.mongo_db`, `settings.mongo_token_usage_collection`.
- Produces: idempotent `chat:{message_id}` ledger docs. Safe to run any number of times, before or after deploy — live writes use the same deterministic `_id`, so backfill and live traffic can never double-count.

- [ ] **Step 1: Write the script** (modeled on `scripts/backfill_tag_dictionary.py`)

```python
"""One-time backfill: materialize existing chat token usage into the ledger.

Joins conversations (owner/workspace) with their assistant messages'
``token_usage`` and upserts one ``token_usage_events`` doc per message with
``_id = chat:{message_id}`` — the same deterministic id live writes use, so
this is idempotent and safe alongside live traffic.

Usage:
    cd services && uv run python scripts/backfill_chat_token_usage.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import sys

import structlog
from motor.motor_asyncio import AsyncIOMotorClient

from infrastructure.config import settings

logger = structlog.get_logger()


async def backfill(dry_run: bool) -> None:
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db]
    ledger = db[settings.mongo_token_usage_collection]

    upserted = 0
    skipped_no_usage = 0
    async for conv in db["conversations"].find(
        {}, {"conversation_id": 1, "workspace_id": 1, "owner_id": 1},
    ):
        cursor = db["chat_messages"].find(
            {
                "conversation_id": conv["conversation_id"],
                "role": "assistant",
                "token_usage": {"$ne": None},
            },
            {"message_id": 1, "token_usage": 1, "created_at": 1},
        )
        async for msg in cursor:
            tu = msg["token_usage"]
            if not tu.get("total"):
                skipped_no_usage += 1
                continue
            doc = {
                "_id": f"chat:{msg['message_id']}",
                "workspace_id": conv.get("workspace_id"),
                "user_id": conv.get("owner_id"),
                "kind": "chat",
                "source": "chat_message",
                "prompt": int(tu.get("prompt", 0)),
                "completion": int(tu.get("completion", 0)),
                "total": int(tu.get("total", 0)),
                "model": None,
                "ref": conv["conversation_id"],
                "created_at": msg["created_at"],
            }
            if not dry_run:
                await ledger.replace_one({"_id": doc["_id"]}, doc, upsert=True)
            upserted += 1

    logger.info(
        "backfill.chat_token_usage.done",
        upserted=upserted,
        skipped_no_usage=skipped_no_usage,
        dry_run=dry_run,
    )


if __name__ == "__main__":
    asyncio.run(backfill(dry_run="--dry-run" in sys.argv))
```

- [ ] **Step 2: Verify against the dev DB** (Mongo must be reachable; skip and note it if the dev stack is down)

Run: `cd services && uv run python scripts/backfill_chat_token_usage.py --dry-run`
Expected: log line with `upserted=<N>` counts and `dry_run=True`, no writes. Then run without `--dry-run` and re-run once more — second run must report the same count (idempotent).

- [ ] **Step 3: Commit**

```bash
git add services/scripts/backfill_chat_token_usage.py
git commit -m "chore(usage): idempotent backfill of historical chat token usage into the ledger"
```

---

## Final verification (after all tasks)

- [ ] `cd services && uv run pytest tests/ -q` — full suite green.
- [ ] `cd web && pnpm --filter portal build` — clean.
- [ ] Grep gates: `grep -rn "else total_tokens" services/infrastructure/chat/` → empty; `grep -rn "get_user_token_usage" services/application/ports/chat_repository.py` → empty.
- [ ] Manual smoke (needs the dev stack + an LLM provider): send a chat message → `token_usage_events` gains one `kind:"chat"` doc with your user id; upload a small PDF → `kind:"ingestion"` docs appear (`page_summary` per page, one `artifact_summary`); `GET /chat/usage?days=30` returns windowed totals; `/stats/member-usage` shows the split; Langfuse trace shows your user id + conversation session.
- [ ] Deploy notes: run the Task 8 backfill on ned after deploy (idempotent, any time). No env changes required (`MONGO_TOKEN_USAGE_COLLECTION` optional). Existing `GET /stats/token-usage` (date/mode chart from `chat_messages`) is intentionally unchanged.

## Explicitly deferred

- **NER token usage** — langextract exposes no usage metadata in its return type; revisit when structflo-ner/langextract can surface it (user decision 2026-07-13).
- **Quota enforcement** — a pre-flight `sum_for_user(days=30)` check in `SendMessageUseCase` + the upload saga, plus limit config; the ledger above is deliberately shaped for it (indexed windowed sums, delete-proof).
- **Materialized per-user counters** — aggregate-on-read is fine at current volume; `$inc` counter docs per (user, month) if `sum_for_user` ever shows up hot.
