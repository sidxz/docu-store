# Dashboard: Recent Chats panel — design

**Date:** 2026-07-02
**Branch:** `ai-elements`
**Status:** approved (design), pending spec review

## Goal

Replace the dashboard's primary panel (currently "Recent Documents", 2/3-width
left column) with a **Recent Chats** panel that is genuinely useful to
scientists — each recent thread recognizable and resumable at a glance — and
move Recent Documents directly below it. Chat is the primary way scientists
interact with the corpus, so it earns the prime real estate.

## Layout

- **Left 2/3 column (stacked):**
  1. **Recent Chats** — header with a `+ New Chat` button top-right, then ~5
     enriched chat cards.
  2. **Recent Documents** — the existing panel, moved here unchanged.
- **Right 1/3 column:** Quick Actions, Recent Searches, Recently Viewed —
  unchanged.

## The recent-chat card

```
┌─────────────────────────────────────────────────────────┐
│ 💬  What is the latest on FadD32?                 2h ago  │
│     NZ-967 identified as lead; IC50 0.08–37 μM across…    │
│     [FadD32·target] [NZ-967·cmpd] [IC50·assay]  4 msgs · ✓ grounded 100% │
└─────────────────────────────────────────────────────────┘
```

- **Title** — conversation title (the question).
- **Snippet** — last assistant answer, stripped to plain text, one line
  (two lines in the no-chips fallback).
- **Chip row (graceful degradation, in priority order):**
  1. Entity chips — top ~4 deduped `ner_entities`, color-coded by type via the
     existing `ui/EntityTypeBadge`. This is the key signal that distinguishes
     near-identical titles.
  2. If zero entities → up to 2 distinct **cited-document** chips
     (`📄 <artifact_title>`, truncated).
  3. If zero entities AND zero sources → no chip row; snippet expands to 2
     lines.
- **Meta row** — relative time · message count · `✓ grounded (NN%)` **only when
  grounded is true** (omitted otherwise; no red "not grounded" noise).
- **Interaction** — click → `/{workspace}/chat/{id}`; hover reveals a delete
  affordance (parity with the sidebar conversation rows).
- **Empty state** — no chats → "Start your first chat" with the New Chat CTA.
- **Count** — 5 cards on the dashboard.

## Data model

The chat **list** endpoint returns only `ConversationDTO` (title, dates,
`message_count`, `model_used`, `is_archived`). The useful metadata lives on the
**messages**: each assistant message persists a `QueryContextDTO`
(`ner_entities: [{entity_text, entity_type}]`, `smiles_detected/resolved`,
`grounded`, `reformulated_query`), plus `sources` (cited artifacts) and
`agent_trace` (grounding confidence). So enrichment aggregates from messages.

## Backend (lean, read-side only)

No new projection or write-path change. Aggregate on read for the top-N only.

- **New DTO** `RecentConversationDTO(ConversationDTO)` adds:
  `last_answer_snippet: str | None`, `entities: list[{text, type}]`,
  `cited_documents: list[{artifact_id, title}]`,
  `source_count: int`, `grounded: bool | None`, `grounded_confidence: float | None`.
- **New use case** `ListRecentConversationsUseCase` — top-N conversations by
  `updated_at` desc, `message_count > 0`; for each, read messages and compute:
  - `last_answer_snippet` = last assistant message content, plain-text
    (strip markdown/LaTeX), truncated (~120 chars).
  - `entities` = union of (a) `ner_entities` across the conversation's messages
    and (b) readable compound identifiers from `smiles_resolved` (`extracted_ids`,
    typed `compound`) so compounds still show as chips when NER misses them;
    deduped by lowercased text, capped at 4, ordered by frequency (ties →
    first-seen), preferring compound/target/assay types when capping.
  - `cited_documents` = distinct cited artifacts (id+title) from message
    `sources`, capped at 2 (fallback chips).
  - `source_count` = distinct cited artifacts.
  - `grounded` / `grounded_confidence` = from the last assistant message's
    grounding (`agent_trace.grounding_is_grounded/confidence`).
- **New repo method** `list_recent_with_summary(workspace_id, owner_id, limit)`
  on `ChatRepository` + Mongo impl. Reuses existing `get_messages`. At N=5 this
  is 5 message reads — cheap; no denormalization.
- **New route** `GET /chat/recent?limit=5` → `list[RecentConversationDTO]`,
  workspace/owner scoped like the existing list route.
- **Tests** — use-case unit test (aggregation/dedup/cap, empty-entity fallback,
  grounded omission, message_count>0 filter); repo method integration test.

## Frontend

- **Types** — `RecentConversation` in `@docu-store/types` mirroring the DTO.
- **Hook** — `useRecentChats(limit = 5)` in `hooks/use-chat.ts` →
  `GET /chat/recent`; shares the chat query-key namespace, invalidated on
  create/delete alongside the list.
- **Component** — `components/dashboard/RecentChatsPanel.tsx` (panel header +
  New Chat button + cards) and a `RecentChatCard`. New Chat reuses
  `useCreateConversation` + router push (same as the sidebar's handler).
- **Dashboard page** — left column becomes `RecentChatsPanel` then the existing
  Recent Documents block; right column unchanged. Chips reuse `EntityTypeBadge`;
  loading uses `Skeleton` cards; snippet uses the app's plain-text helper (or a
  small markdown-strip).

## Out of scope

- No dedicated `/chats` index page ("View all" — the sidebar already lists all;
  may add a subtle link to open chat).
- No denormalized conversation-summary projection (read-side aggregation is
  enough at N=5; revisit only if a full chats index needs it).
- No change to the chat transport, message rendering, or `query_context`
  capture.

## Build order (subagent-driven)

1. Backend: DTO + repo method + use case + route + tests.
2. Frontend: types + hook + RecentChatsPanel/RecentChatCard + dashboard wiring.
3. Review + verify (browser render of the panel with mock data).
