# Chat: Durable Runs, Live Reattach, Ready-Notifications

**Status:** Approved design, 2026-07-14
**Scope:** Chat responses must survive the user navigating away, switching tabs, or reloading. Notify the user when an answer is ready if they are not looking at it.

## Problem

A chat answer takes ~1 minute to synthesize. Today, if the user leaves the chat UI mid-stream, the answer is destroyed on both sides:

1. **Frontend** — `web/apps/portal/src/components/chat/ChatPanel.tsx:49` aborts the SSE fetch on unmount. Any route change kills the stream.
2. **Backend** — `interfaces/api/routes/chat_routes.py` runs `SendMessageUseCase.execute()` *inside* the `StreamingResponse` generator. Client disconnect → Starlette cancels the generator → the pipeline dies mid-flight → the assistant-message save (`application/use_cases/chat_use_cases.py:535`, which runs only after the stream loop completes) never executes. The LLM run is wasted; nothing lands in Mongo. Only token-usage accounting survives (it is in a `finally`).

The Zustand chat store (`lib/stores/chat-store.ts`) is already global and conversation-keyed (`streamingConversationId`) — the stream would survive in-app navigation if the unmount abort didn't kill it.

## Design

### 1. Backend: ChatRunRegistry

New `infrastructure/chat/run_registry.py` (~100 lines), single instance in the DI container.

```
ChatRunRegistry
  _runs: dict[UUID conversation_id → ChatRun]
  start(conversation_id, workspace_id, owner_id, agen) → ChatRun   # RunAlreadyActive if one exists
  subscribe(conversation_id, after: int = -1) → AsyncIterator[str] # replay then tail
  stop(conversation_id) → bool                                     # cancel task, drop run
  active(conversation_id) → ChatRun | None

ChatRun: run_id, workspace_id, owner_id, task: asyncio.Task,
         events: list[str] (serialized SSE frames), done: bool,
         subscribers: list[asyncio.Queue]
```

- `start()` spawns `asyncio.create_task(pump)`. The pump consumes `SendMessageUseCase.execute(...)` **to completion regardless of HTTP clients**: each `AgentEvent` is serialized once into an SSE frame stamped `id: <seq>` (0-based per run), appended to `events`, and fanned out to all subscriber queues. Pipeline exception → emit the existing `error` frame. On finish: `done=True`, sentinel to subscribers, buffer evicted after a ~60s grace (`loop.call_later`) so a reload right at completion can still replay.
- `subscribe(after)` replays `events[after+1:]` and attaches its queue with no `await` between snapshot and attach (single event loop → no gap race), then tails until sentinel.
- `SendMessageUseCase` is **unchanged**. Persist-after-loop now always runs because the pump drives the generator. `stop()` cancels the task → no assistant persisted (today's Stop semantics), usage still recorded via the existing `finally`.
- One active run per conversation. Memory is bounded: one answer's frames ≈ tens of KB.
- `# ponytail: in-memory, assumes single API replica; swap internals to Redis Streams if the API scales out.` On a reattach miss the UX degrades gracefully — the durable answer still appears on refetch.

### 2. Backend: routes (`chat_routes.py`)

| Route | Change |
|---|---|
| `POST /chat/{id}/messages` | `registry.start(...)`; response body = `registry.subscribe(id)` (subscriber #1). `409` if a run is already active. Quota/auth checks unchanged, before start. |
| `GET /chat/{id}/messages/stream?after=<seq>` | **New.** Auth + conversation-ownership check → `subscribe(after)`. `404` if no active/recent run. Full replay rebuilds steps, sources, and partial answer instantly, then tails live. |
| `DELETE /chat/{id}/run` | **New.** Explicit stop for the Stop button (disconnect no longer cancels anything). `204`, or `404` if no run. |
| `GET /chat/{id}` | Conversation detail gains `active_run: bool`. |

SSE frames gain an `id: <seq>` line — additive; the existing frontend parser ignores unknown lines.

### 3. Frontend (`web/apps/portal`)

- **Delete the unmount abort** (`ChatPanel.tsx:49`). The TanStack mutation keeps pumping SSE into the global store across route changes. Abort-before-new-send stays (store is single-buffer).
- **Gate all streaming-derived UI** (`isStreaming`, `streamingContent`, steps, sources, input-disable) by `streamingConversationId === conversationId` — the guard that exists for `pendingUserMessage` (`ChatPanel.tsx:64-68`), now required everywhere since streams outlive their page.
- **Reattach on mount** (`use-chat.ts`): if conversation detail has `active_run` and the store is not already streaming this conversation (e.g. after reload), `GET .../messages/stream` through the existing `processSSEStream` into the store. New store action `resumeStreaming(conversationId)` = `startStreaming` without `pendingUserMessage` (the user message is already persisted — avoids a double bubble). Resume `404` → swallow; refetch shows the final message. Send `409` → reattach instead.
- **Stop button** = local abort + fire-and-forget `DELETE /chat/{id}/run` + `finishStreaming()`.
- Sending in conversation B while A still runs: A's fetch is aborted client-side but the run completes server-side, persists, and remains reattachable. Store shows B (single live view).

### 4. Notifications (frontend-only, native API)

Null-rendering `<ChatNotifications/>` mounted in the **workspace layout** (must outlive the chat routes):

- **Prompt:** when a stream passes ~12s and `Notification.permission === "default"` and no prior dismissal (localStorage flag): one-time toast — "Still working — want a notification when the answer is ready?" → button calls `Notification.requestPermission()` (satisfies the user-gesture requirement). Never re-prompt after dismissal or OS-level denial.
- **Fire** (revised 2026-07-14 after the OS channel proved suppressible — macOS app-level permission/Focus can silently eat banners): on done (not error/stop), split by visibility:
  - **In-app channel (primary, permission-free):** if the user is NOT on that conversation's route → sticky sonner toast (`duration: Infinity`, `id: chat-ready-{convId}` so newer replaces older, "View" action routes to the conversation) AND the conversation is marked unread — a persisted `unreadAnswers: string[]` in the chat store (in the `persist` partialize, so it survives reloads) rendered as an accent dot on the row in `ConversationSidebar`.
  - **OS channel (enhancement):** only when `document.hidden` AND permission granted → `new Notification("Answer ready", {body: first ~120 chars, tag: conversationId})`; click → `window.focus()` + route to the conversation. A visible tab never relies on the suppressible OS path.
  - **Consumption:** landing on `/chat/{id}` (any way — View button, sidebar, reload) dismisses that conversation's toast and clears its unread flag, via a pathname effect in `ChatNotifications`. Deleting a conversation clears its flag.
- The done signal is the still-running mutation or the resume stream — both flow through the store, so one `isStreaming` transition covers both. A fully closed tab gets no notification (Web Push out of scope).

## Coverage matrix

| User action mid-run | Before | After |
|---|---|---|
| Navigate within app | Answer destroyed | Stream continues live in store; return and it's there |
| Switch tab / background | Stream survives but no alert | OS notification on done |
| Reload / close tab / network blip | Answer destroyed server-side | Run completes + persists; reattach replays live state |
| Stop button | Cancels via disconnect | Explicit `DELETE /run`, same discard semantics |
| API restart mid-run | Answer destroyed | Same (in-memory run lost) — accepted |

## Error handling

- Pipeline exception → `error` SSE frame via pump → existing store/render path; nothing persisted.
- Resume/stop on someone else's conversation → same ownership check as every chat route (404).
- Registry entries always evict: on stop, or ~60s after done, or with the process.

## Testing

- **Registry unit tests:** replay+tail correctness, concurrent subscribers, `after` offsets, stop cancellation, done-eviction grace, duplicate-run rejection.
- **Route tests:** 409 on double send, resume 404 (no run / evicted), auth on resume+stop — existing httpx-ASGI streaming patterns.
- **Frontend:** manual browser pass scripted in the implementation plan (navigate-away, reload-reattach, stop, notification prompt+fire). Repo convention: no hook unit tests.

## Deliberate cuts

- No Web Push / service worker (closed-tab notifications) — add when users ask.
- No partial-answer persist on Stop — Stop discards, as today.
- Single live view at a time (store is single-buffer); background runs still complete and persist.
- No Redis — in-memory registry until API replicas > 1.
