# Token Limits & Settings Revamp — Design Spec

**Date:** 2026-07-13
**Status:** Approved (brainstormed + user-validated)
**Depends on:** `token-usage-ledger` branch (append-only `token_usage_events` ledger, `TokenUsageStore` port). Implemented as branch `token-limits` stacked on `token-usage-ledger`.

## Goal

1. Admins can set a **monthly token limit per user**, with a **workspace default**; over-limit users are blocked from chat and uploads.
2. The settings page becomes a **tabbed layout** (sub-routes); **Stats** and **Status** move into it; admin-only tabs are hidden from general users.

## Decisions (user-validated)

| Decision | Choice |
|---|---|
| Limit window | **Calendar month, UTC** — resets on the 1st. Enforcement sums usage since UTC month start. |
| What counts | Chat **and** ingestion tokens (the ledger already unifies them; `total` = prompt + completion). |
| What's blocked | **Chat send and document upload/create** — HTTP 429 pre-flight. |
| Admin exemption | Admins (`auth.is_admin`) are never blocked. |
| Settings structure | **Nested sub-routes** with a vertical tab rail (per-tab code-splitting), not `?tab=`. |
| Enforcement style | Pre-flight check against already-recorded usage. **Soft ceiling**: concurrent in-flight requests can overshoot slightly; no reservations/debits. |

## A. Data model & API (backend)

### Collection `token_limits`

One doc per `(workspace_id, user_id)`:

```
{ _id, workspace_id: UUID, user_id: UUID | null, limit: int | null,
  updated_at: datetime, updated_by: UUID }
```

- `user_id: null` doc = **workspace default**.
- `limit: null` = **unlimited**; `limit: 0` = fully blocked (kill switch). Validation: `limit >= 0` or null.
- **Resolution:** user override row → workspace default row → unlimited. An explicit `null` override makes one user unlimited over a finite default.
- Unique index on `(workspace_id, user_id)` — same pattern as `user_preferences` in `mongo_user_store.py`.
- No row anywhere = unlimited = today's behavior (**no migration needed**).

### Port + adapter

- `application/ports/token_limit_store.py` — `TokenLimitStore` Protocol, dumb CRUD:
  - `get(workspace_id, user_id: UUID | None) -> TokenLimitEntry | None`
  - `list_for_workspace(workspace_id) -> list[TokenLimitEntry]`
  - `set(workspace_id, user_id: UUID | None, limit: int | None, updated_by: UUID) -> None` (upsert)
  - `delete(workspace_id, user_id: UUID) -> None` (remove a user override; the default is cleared by setting it to null)
  - `ensure_indexes() -> None`
- `infrastructure/read_repositories/mongo_token_limit_store.py` — `MongoTokenLimitStore(client, db_name, collection_name)`, mirroring `MongoTokenUsageStore`. Pure module-level doc-mapping helpers for unit tests.
- DTOs in `application/dtos/usage_dtos.py`: `TokenLimitEntry {user_id: UUID | None, limit: int | None}` (+ response models below).
- Config: `mongo_token_limits_collection: str = "token_limits"` (env `MONGO_TOKEN_LIMITS_COLLECTION`) in `infrastructure/config.py`.
- DI registration in `infrastructure/di/container.py` next to the token usage store (~line 853); startup `ensure_indexes()` in the `interfaces/api/main.py` lifespan block, same best-effort try/except as the ledger.

### Admin endpoints (on `interfaces/api/routes/workspace_routes.py`)

All guarded by the inline `if not auth.is_admin: raise HTTPException(403)` used across `/stats`:

- `GET /workspace/token-limits` → `{ default_limit: int | null, overrides: [{ user_id, limit }] }`
- `PUT /workspace/token-limits/default` body `{ limit: int | null }`
- `PUT /workspace/token-limits/{user_id}` body `{ limit: int | null }`
- `DELETE /workspace/token-limits/{user_id}` → user falls back to the workspace default

Routes call the store directly (precedent: `/stats/member-usage` calls `TokenUsageStore.usage_by_member` directly). `updated_at`/`updated_by` are stored for audit but not returned.

## B. Enforcement

### `CheckTokenQuotaUseCase` (`application/use_cases/token_limit_use_cases.py`)

Deps: `TokenLimitStore`, `TokenUsageStore`.

```
execute(workspace_id, user_id) -> None:
    limit = effective_limit(...)          # override ?? default ?? None
    if limit is None: return
    used = (await usage.sum_for_user(ws, user, since=utc_month_start())).total
    if used >= limit: raise TokenLimitExceededError(used, limit)
```

- `effective_limit` is a shared application-layer helper (also used by the extended usage use case, §D).
- `utc_month_start()` = `datetime(now.year, now.month, 1, tzinfo=UTC)`.
- Boundary: `used >= limit` blocks (a user at exactly the limit is blocked).
- `TokenLimitExceededError` lives with the existing application use-case exceptions.

### Route wiring

New helper `ensure_within_quota(auth, container)` in `interfaces/api/routes/helpers.py` (sibling of `require_action`): returns immediately when `auth.is_admin`, otherwise runs the use case and maps `TokenLimitExceededError` to **HTTP 429** with a plain-string detail (no structured parsing anywhere on the FE):

> `"Monthly token limit reached: {used:,} of {limit:,} tokens used. Resets on the 1st (UTC)."`

Call sites (exactly three):
1. `chat_routes.py` `send_message` — before the `StreamingResponse` is constructed, so the client gets a real 429 instead of an in-stream error.
2. `artifact_routes.py` `upload_blob` — immediately after `require_action(auth, "artifacts:create")`.
3. `artifact_routes.py` `create_artifact` — same spot (creation triggers the parse→summarize pipeline, so it costs tokens too).

**Deliberately not gated:** force-resummarize (`POST /artifacts/{id}/summarize`), re-embed/reprocess admin actions — rare, admin-ish maintenance; their usage still counts toward the ledger.

## C. Settings information architecture (frontend)

### Route structure

```
app/[workspace]/settings/
  layout.tsx        ← "Settings" PageHeader + vertical tab rail + admin gating
  page.tsx          ← redirect → ./general
  general/page.tsx    Appearance (theme + font), Developer Mode
  chat/page.tsx       Advanced Reasoning (ReasoningSettings), Default Visibility
  usage/page.tsx      Own month usage vs limit (everyone)
  workspace/page.tsx  Workspace info, Plugins, API Keys placeholder
  tokens/page.tsx     "Token Settings" — admin only
  stats/page.tsx      moved Stats page body — admin only
  status/page.tsx     moved Status page body — admin only
```

- The rail is **styled `next/link`s** (active state from `usePathname()`), visually matching the vertical `TabsList` variant — no radix Tabs needed for sub-routes.
- Admin items (Token Settings, Stats, Status) render under a divider, only when `useAuthzHasRole("admin")`. Each admin page **also** keeps the existing Access-Denied `EmptyState` gate for direct-URL hits (defense in depth; backend endpoints are the real enforcement).
- Existing settings cards move as-is into their tab pages; the empty `components/settings/` dir houses anything extracted. The "Members — coming soon" card is **dropped** (superseded by Token Settings). Zustand stores are untouched.
- Stats/Status: page bodies + their local components (`WorkersSection`, `WorkerCard`, `status-helpers`, etc.) move under the settings routes; their full-size `PageHeader`s become plain section headings (the layout owns the header).
- Old routes `app/[workspace]/stats/page.tsx` and `.../status/page.tsx` become one-line server `redirect()`s to the settings sub-routes (Next 16: `params` is async).
- `Sidebar.tsx`: remove the Stats and Status entries from `mainNav`; if `requireAdmin` is then unused, delete the field and its filter.

## D. Token Settings tab, Usage tab, Topbar badge

### `GET /chat/usage` extension (backend)

Response keeps today's shape and adds a `month` object (consumers: badge + Usage tab only):

```
{ prompt, completion, total,                      // requested window (days/kind), as today
  month: { chat: int, ingestion: int, total: int, limit: int | null } }
```

- `month.*` = current UTC calendar month; per-kind values are token totals; `limit` = caller's effective limit.
- `GetUserTokenUsageUseCase` gains the `TokenLimitStore` dep + the shared `effective_limit` helper. Cost: 2–3 extra indexed aggregations per 60s badge poll — fine at current scale; the ledger already carries a `ponytail:` materialized-counter upgrade note.
- FE `TokenUsage` type in `packages/types` extended with the optional `month` field.

### Token Settings tab (admin)

- **Workspace default card**: shows current default (or "Unlimited"), edit + save.
- **Members table** joining three sources by `user_id` (FE-side join, precedent: existing stats member card):
  1. `GET /workspace/members` — identities (Duar; 50-member cap, same as the stats card today),
  2. `GET /stats/member-usage?period=month` — current-month usage,
  3. `GET /workspace/token-limits` — limits.
- Columns: member (name/email), month usage, effective limit with a `default`/`override` badge, actions (set override / clear override → falls back to default).
- New hook file `apps/portal/src/hooks/use-token-limits.ts` (`authFetchJson` + manual types, like all stats/admin hooks) + `queryKeys.workspace.tokenLimits()`; mutations invalidate that key.

### Usage tab (everyone)

- Month progress bar: `month.total` vs `month.limit`, **amber ≥ 80%, red at 100%**; when unlimited, no bar — just the plain month total.
- Chat vs ingestion split for the month.
- Copy: "Resets on the 1st (UTC)."

### Topbar badge

- Switches from all-time total to **`month.total`**, appends `/ {limit}` when a limit is set, amber ≥ 80% / red ≥ 100%. (Semantic change: current month is the meaningful number once limits exist.)

## E. Over-limit UX

- **Chat:** send request 429s before the stream opens; the chat UI surfaces the detail string through its existing send/stream error path.
- **Upload:** `authFetchJson` already throws `ApiError` carrying the FastAPI detail → upload page's existing error state shows the message.
- Admins never hit either path.

## F. Testing

Backend (patterns already in the repo — fakes, no real Mongo):

- `CheckTokenQuotaUseCase` with `FakeLimitStore`/`FakeUsageStore`: unlimited passes; under passes; `used == limit` blocks; override beats default; `null` override = unlimited over finite default; limit 0 blocks.
- Route tests via the `test_stats_member_usage.py` template (`TestClient` + `FakeAuth` + `FakeContainer`): limits CRUD → 403 viewer / 200 admin; chat send + upload → 429 over limit with the detail string; admin over limit → passes.
- Pure helper tests for `MongoTokenLimitStore` doc mapping (module-level helpers), like `test_token_usage_store.py`.
- Extended `GetUserTokenUsageUseCase`: `month` block present, `limit` resolution correct.
- Our route tests will be the 3rd+ copy of `_strip_authz_middleware` → **extract it to `tests/conftest.py`** as part of this work (known follow-up from the ledger review).

Frontend: `pnpm tsc` + build green; manual browser pass (tab gating as admin vs viewer, limit editing, over-limit chat + upload errors, badge states).

## G. Rollout & dependencies

- Branch `token-limits` stacked on `token-usage-ledger`; merge after (or together with) the ledger. Reminder: the unrelated NER fix `134aa7a` on the ledger branch still needs its cherry-pick decision before merge.
- No data migration; absent limits = unlimited. Purely additive.
- No OpenAPI regen needed — the admin surface uses `authFetchJson` with manual types.

## Out of scope

- Reservation/debit-style hard ceilings (soft ceiling accepted).
- Gating force-resummarize or admin maintenance actions.
- Per-workspace/user *model* configuration (see BYO-LLM deferred design).
- NER token counting (langextract exposes no usage; deferred).
- Materialized usage counters (upgrade path noted in the ledger).
