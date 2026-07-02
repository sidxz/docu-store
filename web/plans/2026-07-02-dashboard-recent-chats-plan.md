# Dashboard Recent Chats — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace the dashboard's primary panel with an enriched "Recent Chats" panel (entity/compound chips, answer snippet, grounded signal) and move Recent Documents below it.

**Architecture:** New read-only backend endpoint `GET /chat/recent?limit=5` aggregates a per-conversation summary from message `query_context`/`sources` for the top-N recent conversations (no denormalization). Frontend adds a `useRecentChats` hook and a `RecentChatsPanel`/`RecentChatCard`, and restacks the dashboard's left column.

**Tech Stack:** Backend — FastAPI, lagom DI, Motor (async Mongo), pydantic, `returns.result` (Success/Failure), pytest-asyncio. Frontend — Next.js 16, TanStack Query v5, Tailwind v4, shadcn/ui.

**Spec:** `web/plans/2026-07-02-dashboard-recent-chats-design.md`

## Global Constraints

- Backend use cases return `Result[T, AppError]` (`returns.result`); routes are decorated `@handle_use_case_errors` and return the unwrapped value.
- Backend workspace/owner scoping: routes read `auth.workspace_id` / `auth.user_id` from `Depends(get_auth)`.
- Run backend tests with `uv run pytest` from `services/`.
- Frontend hand-authors domain types in `web/packages/types/src/domain/chat.ts` (NOT generated); hooks fetch via `authFetchJson<T>` from `@/lib/auth-fetch`.
- Frontend verify: `cd web/apps/portal && pnpm lint` (tsc --noEmit) must pass; a dev server runs on :15000 — do NOT start another, do NOT `pnpm build`.
- Recent chats shown: 5. Entity chips capped at 4. Snippet ~120 chars. Grounded pill only when `grounded === true`. Conversations with `message_count === 0` are excluded (backend filter).

---

### Task 1: Backend — `GET /chat/recent` enriched summaries

**Files:**
- Modify: `services/application/dtos/chat_dtos.py` (add `EntityRefDTO`, `CitedDocumentDTO`, `RecentConversationDTO` after `ConversationDetailDTO`, ~line 194)
- Modify: `services/application/ports/chat_repository.py` (add `list_recent_conversations` to the `ChatRepository` Protocol)
- Modify: `services/infrastructure/chat/mongo_chat_repository.py` (implement `list_recent_conversations`)
- Modify: `services/application/use_cases/chat_use_cases.py` (add `ListRecentConversationsUseCase` + module-level `_build_recent_summary` helpers)
- Modify: `services/infrastructure/di/container.py` (register the use case near `ListConversationsUseCase`, ~line 914; add to the import list ~line 55)
- Modify: `services/interfaces/api/routes/chat_routes.py` (add `GET /chat/recent`; import `RecentConversationDTO` and `ListRecentConversationsUseCase`)
- Test: `services/tests/application/test_recent_conversations_use_case.py`

**Interfaces:**
- Produces (repo): `async def list_recent_conversations(self, workspace_id: UUID, owner_id: UUID, limit: int) -> list[ConversationDTO]` — `is_archived=False`, `message_count > 0`, sorted `updated_at` desc, limited.
- Produces (use case): `ListRecentConversationsUseCase(chat_repository).execute(workspace_id: UUID, owner_id: UUID, limit: int = 5) -> Result[list[RecentConversationDTO], AppError]`.
- Produces (route): `GET /chat/recent?limit=5 -> list[RecentConversationDTO]`.
- Consumes (existing): `repo.get_messages(conversation_id) -> list[ChatMessageDTO]`; `ChatMessageDTO.query_context: QueryContextDTO | None` (`ner_entities: list[dict]` with keys `entity_text`/`entity_type`; `smiles_resolved: list[dict]` with key `extracted_ids: list[str]`); `ChatMessageDTO.sources: list[SourceCitationDTO]` (`artifact_id`, `artifact_title`); `ChatMessageDTO.agent_trace: AgentTraceDTO | None` (`grounding_is_grounded`, `grounding_confidence`).

- [ ] **Step 1: Add DTOs**

In `chat_dtos.py`, after `ConversationDetailDTO`:

```python
class EntityRefDTO(BaseModel):
    """A named entity discussed in a conversation (for recent-chat chips)."""
    text: str
    type: str


class CitedDocumentDTO(BaseModel):
    """A document cited in a conversation (fallback chip)."""
    artifact_id: UUID
    title: str | None = None


class RecentConversationDTO(ConversationDTO):
    """A conversation enriched with a summary for the dashboard recent-chats panel."""
    last_answer_snippet: str | None = None
    entities: list[EntityRefDTO] = Field(default_factory=list)
    cited_documents: list[CitedDocumentDTO] = Field(default_factory=list)
    source_count: int = 0
    grounded: bool | None = None
    grounded_confidence: float | None = None
```

- [ ] **Step 2: Write the failing use-case test**

Create `services/tests/application/test_recent_conversations_use_case.py`:

```python
"""ListRecentConversationsUseCase — enriched recent-chat summaries."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from returns.result import Success

from application.dtos.chat_dtos import (
    AgentTraceDTO,
    ChatMessageDTO,
    ConversationDTO,
    QueryContextDTO,
    SourceCitationDTO,
)
from application.use_cases.chat_use_cases import ListRecentConversationsUseCase


def _conv(cid, ws, owner, *, msgs=2, updated=None) -> ConversationDTO:
    now = updated or datetime(2026, 7, 1, tzinfo=UTC)
    return ConversationDTO(
        conversation_id=cid, workspace_id=ws, owner_id=owner,
        title="Latest on FadD32?", created_at=now, updated_at=now,
        message_count=msgs, model_used="claude", is_archived=False,
    )


def _asst(cid, content, *, entities=(), smiles=(), sources=(), grounded=None, conf=None):
    qc = QueryContextDTO(
        ner_entities=[{"entity_text": t, "entity_type": ty} for t, ty in entities],
        smiles_resolved=[{"extracted_ids": list(smiles)}] if smiles else [],
    )
    trace = AgentTraceDTO(grounding_is_grounded=grounded, grounding_confidence=conf)
    return ChatMessageDTO(
        conversation_id=cid, message_id=uuid4(), role="assistant", content=content,
        sources=[SourceCitationDTO(artifact_id=a, artifact_title=t, citation_index=i)
                 for i, (a, t) in enumerate(sources)],
        query_context=qc, agent_trace=trace, created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


class _FakeRepo:
    def __init__(self, convs, messages):
        self._convs = convs
        self._messages = messages  # {conversation_id: [ChatMessageDTO]}
        self.limit_seen = None

    async def list_recent_conversations(self, workspace_id, owner_id, limit):
        self.limit_seen = limit
        return self._convs

    async def get_messages(self, conversation_id, skip=0, limit=100):
        return self._messages.get(conversation_id, [])


@pytest.mark.asyncio
async def test_enriches_entities_snippet_grounding():
    ws, owner, cid = uuid4(), uuid4(), uuid4()
    art = uuid4()
    convs = [_conv(cid, ws, owner)]
    messages = {cid: [
        _asst(cid, "## Heading\nNZ-967 is the **lead** with $IC_{50}$ 0.08 uM.",
              entities=[("FadD32", "target"), ("FadD32", "target"), ("IC50", "assay")],
              smiles=["NZ-967"], sources=[(art, "FadD32 updates")],
              grounded=True, conf=1.0),
    ]}
    repo = _FakeRepo(convs, messages)

    result = await ListRecentConversationsUseCase(repo).execute(ws, owner, limit=5)

    assert isinstance(result, Success)
    [rc] = result.unwrap()
    assert repo.limit_seen == 5
    # snippet is plain-text (no markdown/latex), truncated
    assert "NZ-967 is the lead" in rc.last_answer_snippet
    assert "**" not in rc.last_answer_snippet and "$" not in rc.last_answer_snippet
    # entities deduped (FadD32 once) + compound from smiles, capped at 4
    texts = {e.text for e in rc.entities}
    assert "FadD32" in texts and "IC50" in texts and "NZ-967" in texts
    assert len(rc.entities) <= 4
    assert any(e.type == "compound" and e.text == "NZ-967" for e in rc.entities)
    # cited docs + grounding
    assert rc.cited_documents[0].title == "FadD32 updates"
    assert rc.source_count == 1
    assert rc.grounded is True and rc.grounded_confidence == 1.0


@pytest.mark.asyncio
async def test_generic_chat_no_entities_no_sources():
    ws, owner, cid = uuid4(), uuid4(), uuid4()
    convs = [_conv(cid, ws, owner)]
    messages = {cid: [_asst(cid, "Yes, they are affiliated with Texas A&M.")]}
    result = await ListRecentConversationsUseCase(_FakeRepo(convs, messages)).execute(ws, owner)
    [rc] = result.unwrap()
    assert rc.entities == []
    assert rc.cited_documents == []
    assert rc.grounded is None  # omitted, no red flag
    assert "Texas A&M" in rc.last_answer_snippet
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd services && uv run pytest tests/application/test_recent_conversations_use_case.py -v`
Expected: FAIL with `ImportError`/`AttributeError` (`ListRecentConversationsUseCase` not defined).

- [ ] **Step 4: Implement the use case**

In `chat_use_cases.py` add imports (`RecentConversationDTO, EntityRefDTO, CitedDocumentDTO` from `application.dtos.chat_dtos`; `re`) and:

```python
# link pattern BEFORE the single-char class, else "[" strips first and leaves "(url)"
_MD_STRIP = re.compile(r"(\$[^$]*\$|!?\[[^\]]*\]\([^)]*\)|[*#`_>\[\]])")


def _plain_text(text: str) -> str:
    return re.sub(r"\s+", " ", _MD_STRIP.sub("", text)).strip()


def _build_recent_summary(conv, messages) -> RecentConversationDTO:
    assistant = [m for m in messages if m.role == "assistant"]
    last = assistant[-1] if assistant else None
    snippet = _plain_text(last.content)[:120] if last and last.content else None

    order: list[tuple[str, str]] = []       # (lower_text, ...) preserves first-seen order
    counts: dict[str, int] = {}
    labels: dict[str, tuple[str, str]] = {}  # lower -> (text, type)

    def add(text, etype):
        if not text:
            return
        key = text.lower()
        if key not in labels:
            labels[key] = (text, etype or "other")
            order.append((key, etype or "other"))
        counts[key] = counts.get(key, 0) + 1

    for m in messages:
        qc = m.query_context
        if not qc:
            continue
        for e in qc.ner_entities:
            add(e.get("entity_text"), e.get("entity_type"))
        for sr in qc.smiles_resolved:
            for cid in sr.get("extracted_ids", []):
                add(cid, "compound")

    _PRI = {"compound": 0, "compound_name": 0, "target": 1, "gene": 1, "assay": 2}
    ranked = sorted(order, key=lambda o: (_PRI.get(o[1], 9), -counts[o[0]]))
    entities = [EntityRefDTO(text=labels[k][0], type=labels[k][1]) for k, _ in ranked[:4]]

    seen_art: dict = {}
    for m in messages:
        for s in m.sources:
            seen_art.setdefault(s.artifact_id, s.artifact_title)
    cited = [CitedDocumentDTO(artifact_id=a, title=t) for a, t in list(seen_art.items())[:2]]

    trace = last.agent_trace if last else None
    return RecentConversationDTO(
        **conv.model_dump(),
        last_answer_snippet=snippet,
        entities=entities,
        cited_documents=cited,
        source_count=len(seen_art),
        grounded=(trace.grounding_is_grounded if trace else None),
        grounded_confidence=(trace.grounding_confidence if trace else None),
    )


class ListRecentConversationsUseCase:
    """Top-N recent conversations enriched with a UI summary."""

    def __init__(self, chat_repository: ChatRepository) -> None:
        self._repo = chat_repository

    async def execute(
        self, workspace_id: UUID, owner_id: UUID, limit: int = 5,
    ) -> Result[list[RecentConversationDTO], AppError]:
        try:
            convs = await self._repo.list_recent_conversations(
                workspace_id=workspace_id, owner_id=owner_id, limit=limit,
            )
            out = []
            for conv in convs:
                messages = await self._repo.get_messages(conv.conversation_id)
                out.append(_build_recent_summary(conv, messages))
            return Success(out)
        except Exception as e:  # noqa: BLE001
            log.exception("chat.recent.list_failed", error=str(e))
            return Failure(AppError("internal_error", f"Failed to list recent chats: {e!s}"))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd services && uv run pytest tests/application/test_recent_conversations_use_case.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Add the repo port + Mongo method**

In `application/ports/chat_repository.py`, inside the `ChatRepository` Protocol (near `list_conversations`):

```python
    async def list_recent_conversations(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        limit: int,
    ) -> list[ConversationDTO]: ...
```

In `infrastructure/chat/mongo_chat_repository.py`, after `list_conversations`:

```python
    async def list_recent_conversations(
        self,
        workspace_id: UUID,
        owner_id: UUID,
        limit: int,
    ) -> list[ConversationDTO]:
        query = {
            "workspace_id": str(workspace_id),
            "owner_id": str(owner_id),
            "is_archived": False,
            "message_count": {"$gt": 0},
        }
        cursor = self._conversations.find(query).sort("updated_at", -1).limit(limit)
        return [_doc_to_conversation(doc) async for doc in cursor]
```

- [ ] **Step 7: Register in DI + add the route**

In `infrastructure/di/container.py`: add `ListRecentConversationsUseCase` to the chat use-case import block (~line 55) and register near `ListConversationsUseCase` (~line 914):

```python
    container[ListRecentConversationsUseCase] = lambda c: ListRecentConversationsUseCase(
        chat_repository=c[ChatRepository],
    )
```

In `interfaces/api/routes/chat_routes.py`: add `RecentConversationDTO` to the `chat_dtos` import and `ListRecentConversationsUseCase` to the use-case import, then add BEFORE the `/{conversation_id}` route (so `/recent` isn't captured as an id):

```python
@router.get("/recent", status_code=status.HTTP_200_OK)
@handle_use_case_errors
async def list_recent_conversations(
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
    limit: int = 5,
) -> list[RecentConversationDTO]:
    """Recent conversations enriched with a dashboard summary."""
    use_case = container[ListRecentConversationsUseCase]
    return await use_case.execute(
        workspace_id=auth.workspace_id,
        owner_id=auth.user_id,
        limit=limit,
    )
```

- [ ] **Step 8: Run full chat test suite + commit**

Run: `cd services && uv run pytest tests/application/test_recent_conversations_use_case.py tests/interfaces -q` (and any chat route tests).
Expected: PASS.

```bash
git add services/application services/infrastructure services/interfaces services/tests/application/test_recent_conversations_use_case.py
git commit -m "feat(chat): GET /chat/recent enriched recent-conversation summaries"
```

---

### Task 2: Frontend — types + `useRecentChats` hook

**Files:**
- Modify: `web/packages/types/src/domain/chat.ts` (add `EntityRef`, `CitedDocument`, `RecentConversation`)
- Modify: `web/apps/portal/src/hooks/use-chat.ts` (add `useRecentChats`)
- Modify: `web/apps/portal/src/lib/query-keys.ts` (add `chat.recent(limit)` key)

**Interfaces:**
- Produces: `RecentConversation` type; `useRecentChats(limit?: number)` returning TanStack Query `{ data: RecentConversation[] | undefined, isLoading, ... }`.
- Consumes: `authFetchJson` from `@/lib/auth-fetch`; existing `Conversation` type; `queryKeys.chat`.

- [ ] **Step 1: Add types**

In `web/packages/types/src/domain/chat.ts`, after `Conversation`:

```typescript
export interface EntityRef {
  text: string;
  type: string;
}

export interface CitedDocument {
  artifact_id: string;
  title: string | null;
}

export interface RecentConversation extends Conversation {
  last_answer_snippet: string | null;
  entities: EntityRef[];
  cited_documents: CitedDocument[];
  source_count: number;
  grounded: boolean | null;
  grounded_confidence: number | null;
}
```

- [ ] **Step 2: Add the query key**

In `web/apps/portal/src/lib/query-keys.ts`, inside the `chat` block:

```typescript
    recent: (limit: number) => [...queryKeys.chat.all, "recent", limit] as const,
```

- [ ] **Step 3: Add the hook**

In `web/apps/portal/src/hooks/use-chat.ts`, import `RecentConversation` alongside `Conversation`, and after `useConversations`:

```typescript
export function useRecentChats(limit = 5) {
  return useQuery({
    queryKey: queryKeys.chat.recent(limit),
    queryFn: () => authFetchJson<RecentConversation[]>(`/chat/recent?limit=${limit}`),
    staleTime: 30_000,
  });
}
```

Also add `queryClient.invalidateQueries({ queryKey: queryKeys.chat.all })`-style invalidation already covers recent via `chat.all` prefix in `useCreateConversation`/`useDeleteConversation` (verify they invalidate `chat.all` or `chat.list`; if only `chat.list`, broaden to `chat.all` so recent refreshes).

- [ ] **Step 4: Verify + commit**

Run: `cd web/apps/portal && pnpm lint`
Expected: PASS.

```bash
git add web/packages/types/src/domain/chat.ts web/apps/portal/src/hooks/use-chat.ts web/apps/portal/src/lib/query-keys.ts
git commit -m "feat(web): RecentConversation type + useRecentChats hook"
```

---

### Task 3: Frontend — RecentChatsPanel + dashboard wiring

**Files:**
- Create: `web/apps/portal/src/lib/entity-colors.ts` (NER entity-type → chip style, extracted from EntityTagPanel's map)
- Create: `web/apps/portal/src/components/dashboard/RecentChatCard.tsx`
- Create: `web/apps/portal/src/components/dashboard/RecentChatsPanel.tsx`
- Modify: `web/apps/portal/src/app/[workspace]/page.tsx` (left column: RecentChatsPanel above the existing Recent Documents block)

**Interfaces:**
- Consumes: `useRecentChats` (Task 2), `RecentConversation`/`EntityRef` types, `useCreateConversation`, `useChatStore().reset`, `useRouter`, `Skeleton`, `Badge`.
- Produces: `RecentChatsPanel({ workspace }: { workspace: string })`.

- [ ] **Step 1: Entity-color helper**

Create `web/apps/portal/src/lib/entity-colors.ts`:

```typescript
// NER entity-type → chip style. Mirrors EntityTagPanel's map; keep in sync.
const STYLES: Record<string, string> = {
  compound: "border-emerald-500/30 text-emerald-700 dark:text-emerald-400",
  compound_name: "border-emerald-500/30 text-emerald-700 dark:text-emerald-400",
  target: "border-amber-500/30 text-amber-700 dark:text-amber-400",
  gene: "border-amber-500/30 text-amber-700 dark:text-amber-400",
  assay: "border-blue-500/30 text-blue-700 dark:text-blue-400",
  disease: "border-rose-500/30 text-rose-700 dark:text-rose-400",
};
const FALLBACK = "border-zinc-400/30 text-zinc-600 dark:text-zinc-400";

export function entityChipClass(type: string): string {
  return STYLES[type] ?? FALLBACK;
}
```

- [ ] **Step 2: RecentChatCard**

Create `web/apps/portal/src/components/dashboard/RecentChatCard.tsx`:

```tsx
"use client";

import Link from "next/link";
import { MessageSquare, FileText, ShieldCheck } from "lucide-react";
import type { RecentConversation } from "@docu-store/types";
import { entityChipClass } from "@/lib/entity-colors";
import { formatRelativeTime } from "@/lib/utils";

export function RecentChatCard({ chat, workspace }: { chat: RecentConversation; workspace: string }) {
  const hasChips = chat.entities.length > 0;
  const hasDocs = !hasChips && chat.cited_documents.length > 0;
  return (
    <Link
      href={`/${workspace}/chat/${chat.conversation_id}`}
      className="group block rounded-xl border border-border-default bg-surface-elevated p-4 transition-all hover:border-primary/30 hover:shadow-ds-sm"
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-light">
          <MessageSquare className="h-4 w-4 text-accent-text" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-3">
            <p className="truncate text-sm font-medium text-text-primary">{chat.title || "New Chat"}</p>
            <span className="shrink-0 text-xs text-text-muted">{formatRelativeTime(chat.updated_at)}</span>
          </div>
          {chat.last_answer_snippet && (
            <p className={`mt-0.5 text-xs text-text-muted ${hasChips || hasDocs ? "line-clamp-1" : "line-clamp-2"}`}>
              {chat.last_answer_snippet}
            </p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {hasChips &&
              chat.entities.map((e) => (
                <span
                  key={`${e.type}-${e.text}`}
                  className={`inline-flex items-center rounded-md border bg-surface-elevated px-1.5 py-0.5 text-[11px] font-medium ${entityChipClass(e.type)}`}
                >
                  {e.text}
                </span>
              ))}
            {hasDocs &&
              chat.cited_documents.map((d) => (
                <span
                  key={d.artifact_id}
                  className="inline-flex max-w-[12rem] items-center gap-1 truncate rounded-md border border-border-default bg-surface-elevated px-1.5 py-0.5 text-[11px] text-text-secondary"
                >
                  <FileText className="h-3 w-3 shrink-0 text-text-muted" />
                  <span className="truncate">{d.title ?? "Document"}</span>
                </span>
              ))}
            <span className="ml-auto flex items-center gap-2 text-[11px] text-text-muted">
              <span>{chat.message_count} msgs</span>
              {chat.grounded === true && (
                <span className="flex items-center gap-0.5 text-ds-success">
                  <ShieldCheck className="h-3 w-3" />
                  {chat.grounded_confidence != null ? `${Math.round(chat.grounded_confidence * 100)}%` : "grounded"}
                </span>
              )}
            </span>
          </div>
        </div>
      </div>
    </Link>
  );
}
```

If `formatRelativeTime` does not exist in `web/apps/portal/src/lib/utils.ts`, add it:

```typescript
export function formatRelativeTime(iso: string): string {
  const d = new Date(iso);
  const s = Math.floor((Date.now() - d.getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 604800) return `${Math.floor(s / 86400)}d ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
```

- [ ] **Step 3: RecentChatsPanel**

Create `web/apps/portal/src/components/dashboard/RecentChatsPanel.tsx`:

```tsx
"use client";

import { useRouter } from "next/navigation";
import { Plus, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecentChats, useCreateConversation } from "@/hooks/use-chat";
import { useChatStore } from "@/lib/stores/chat-store";
import { RecentChatCard } from "./RecentChatCard";

export function RecentChatsPanel({ workspace }: { workspace: string }) {
  const router = useRouter();
  const { data: chats, isLoading } = useRecentChats(5);
  const createConversation = useCreateConversation();
  const resetChat = useChatStore((s) => s.reset);

  const handleNew = async () => {
    resetChat();
    const conv = await createConversation.mutateAsync(undefined);
    router.push(`/${workspace}/chat/${conv.conversation_id}`);
  };

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text-primary">Recent Chats</h2>
        <Button size="sm" onClick={handleNew} disabled={createConversation.isPending}>
          <Plus className="size-4" />
          New Chat
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-xl border border-border-default bg-surface-elevated p-4">
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="mt-2 h-3 w-3/4" />
            </div>
          ))}
        </div>
      ) : !chats?.length ? (
        <div className="flex flex-col items-center rounded-xl border border-border-default bg-surface-elevated py-10 text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-accent-light">
            <MessageSquare className="h-6 w-6 text-accent-text" />
          </div>
          <p className="text-sm font-medium text-text-primary">No chats yet</p>
          <p className="mt-1 text-xs text-text-muted">Start your first chat to explore your documents.</p>
          <Button size="sm" className="mt-4" onClick={handleNew} disabled={createConversation.isPending}>
            <Plus className="size-4" />
            New Chat
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {chats.map((chat) => (
            <RecentChatCard key={chat.conversation_id} chat={chat} workspace={workspace} />
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Wire into the dashboard**

In `web/apps/portal/src/app/[workspace]/page.tsx`: import `RecentChatsPanel`. In the left 2/3 column (`<div className="lg:col-span-2 ...">` block currently holding Recent Documents), keep the Recent Documents block but wrap the column so RecentChatsPanel renders ABOVE it. Concretely, replace the two-column grid's left child with:

```tsx
<div className="space-y-8 lg:col-span-2">
  <RecentChatsPanel workspace={workspace} />
  <div className="rounded-xl border border-border-default bg-surface-elevated">
    {/* existing Recent Documents panel — unchanged */}
    ...
  </div>
</div>
```

(The existing Recent Documents `<div className="lg:col-span-2 rounded-xl ...">` becomes the inner `<div className="rounded-xl ...">` — drop its `lg:col-span-2` since the wrapper now carries it.)

- [ ] **Step 5: Verify + commit**

Run: `cd web/apps/portal && pnpm lint`
Expected: PASS. Then confirm the panel renders (browser render of the dashboard/component with mock `RecentConversation[]`, both themes: entity-chip case, cited-doc fallback case, and no-chip snippet case).

```bash
git add web/apps/portal/src/lib/entity-colors.ts web/apps/portal/src/components/dashboard/ "web/apps/portal/src/app/[workspace]/page.tsx" web/apps/portal/src/lib/utils.ts
git commit -m "feat(web): dashboard Recent Chats panel; move Recent Documents below"
```

---

## Notes for the implementer

- The chip color helper deliberately uses the `text-*-{600|700} dark:text-*-400` theme-correctness convention (light mode is a real theme here).
- Do not fetch conversation detail from the frontend to build chips — the `/chat/recent` endpoint already aggregates it.
- Keep Recent Documents' markup byte-identical; only relocate it under the new panel.
- Delete-on-hover (mentioned in the spec) is DEFERRED: the card is a `<Link>`, and a nested delete button adds `stopPropagation`/mutation complexity for little gain since the sidebar already offers delete. Add later if the user wants it.
