# Chat Reasoning Controls — FE-driven per-request reasoning

**Status:** Approved design — pending implementation plan
**Date:** 2026-06-26
**Author:** sidx
**Related:** `MULTI_PROVIDER_LLM.md` §4.3 (the deferred "dynamic per-mode switching"),
`CHAT_REASONING_DISCLOSURE.md` (surfaces the synthesis reasoning this controls)

## 1. Context

Per-lane reasoning exists (`CHAT_LLM_REASONING` / `CHAT_SYNTHESIS_REASONING` /
`CHAT_RETRIEVAL_REASONING`) but is **construction-time, env-only**: the three lane
clients are built once at container startup. Changing reasoning means editing
`.env` and restarting. This feature lets the frontend control reasoning live —
a per-message composer toggle plus a settings panel of persisted defaults — by
applying reasoning **per request** instead of per construction.

The lanes map to clients (and the nodes they feed):
- **synthesis** → `chat_synthesis_llm_client` (QueryPlanning, AdaptiveSynthesis, InlineVerification) — the only lane with a UI surface (the reasoning disclosure)
- **retrieval** → `tool_calling_llm` (AgenticRetrieval loop)
- **base** → `chat_llm_client` (QuestionAnalysis, AnswerSynthesis, GroundingVerification, AnswerFormatting)

## 2. Goals / Non-goals

**Goals**
- Control all three reasoning lanes from the FE: a per-message synthesis toggle in
  the composer, and a settings panel of persisted per-lane + effort defaults.
- Apply reasoning per request; no behavior change when the request omits it.
- No new backend storage — the FE holds the settings and sends the effective
  levels in the chat request body.

**Non-goals**
- Server-side / cross-device settings sync (client-side localStorage by decision).
- Surfacing retrieval/base reasoning in the chat UI (only synthesis is visible).
- Streaming reasoning for retrieval/base lanes (only synthesis emits `reasoning_token`).

## 3. Control model & precedence

- **FE-persisted defaults** (zustand `persist` → localStorage):
  `reasoningDefaults = { synthesis, retrieval, base }`, each `off|low|medium|high`.
  Edited in the settings panel.
- **Composer toggle** — a per-message "Reasoning" on/off for the **synthesis** lane.
  `on` → the persisted synthesis level (or `medium` if persisted is `off`);
  `off` → forces synthesis `off` for that message. Session-scoped (reflects the
  persisted default on load).
- **Each chat request** sends the effective levels:
  `reasoning: { synthesis, retrieval, base }` in the body (next to `mode`).
- **Backend precedence per lane:** request-supplied level → else the lane's env
  default (`CHAT_*_REASONING`). An absent `reasoning` object = today's behavior.

## 4. Backend — apply reasoning per request

### 4.1 Request

`SendMessageRequest` gains optional
`reasoning: ReasoningOverride | None` where
`ReasoningOverride = { synthesis?: Level, retrieval?: Level, base?: Level }`,
`Level = Literal["off","low","medium","high"]`. Threaded into
`SendMessageUseCase.execute(..., reasoning=None)` exactly as `mode` is today.

### 4.2 Mechanism — request-scoped ContextVar (chosen)

A module-level `reasoning_override: ContextVar[dict[str, str] | None]` (lane→level).
`SendMessageUseCase.execute` sets it from the request at the top of the body
(reset in a `finally`). Each lane client is **lane-aware** (constructed with
`lane="synthesis"|"retrieval"|"base"`) and, in `_get_llm()`, resolves its effective
level as `reasoning_override.get().get(self._lane)` if present, else its
env-configured `self._reasoning`. Models are cached **per level**
(`self._models: dict[str, BaseChatModel]`, built lazily via `build_chat_model`),
so the construction-time reasoning constraint is honoured without `.bind()`
(which §4.3 flagged as unsafe). The node and agent code is **unchanged** — every
LLM method routes through `_get_llm()`, so reading the contextvar there covers
`complete` / `stream` / `stream_with_reasoning` / `complete_structured` /
`complete_with_image` and the tool adapter uniformly.

**Why ContextVar over explicit threading:** threading the level to the call sites
would add a `reasoning` parameter to every LLM port method *and* every LLM-using
node `run()` (7 nodes) *and* both agent `run()` signatures — a large, invasive
diff for a request-scoped value. A contextvar read in `_get_llm()` is the
idiomatic tool and touches only the adapters + use case + DTO.

**The one risk — propagation (spike-gated, §8):** the contextvar is set inside the
use case's async-generator body; the adapters read it several `await`s deep inside
`agent.run()` (also an async generator) consumed by the SSE route. Async-generator
context propagation has known subtleties. **Implementation spikes this first**
(§8) with a test that asserts a level set in `execute` reaches a fake adapter
through the real pipeline. If it does not propagate reliably, fall back to
explicit threading (larger diff, identical behavior) — captured as the
contingency in the plan.

### 4.3 Concurrency

Lane clients are shared singletons across concurrent requests, so per-request
reasoning must NOT be stored as mutable client state (request bleed). The
ContextVar is the correct tool — per-request, per-task isolation. The per-level
model cache is read-mostly and keyed by level (immutable models), safe to share.

## 5. Frontend

- **chat-store** (`apps/portal/src/lib/stores/chat-store.ts`, persisted slice):
  `reasoningDefaults: { synthesis, retrieval, base }` (persisted) + a session
  `synthesisOverride: "on" | "off" | null` (null = follow default). A selector
  computes the effective `reasoning` object to send.
- **Request** (`use-chat.ts`): include `reasoning` in the POST body next to `mode`.
- **Composer** (`components/chat/ChatInput.tsx`): a "Reasoning" toggle beside the
  mode picker, bound to `synthesisOverride`.
- **Settings panel** (`app/[workspace]/settings/page.tsx` + a new
  `ReasoningSettings` component): three lane selects (synthesis/retrieval/base) ×
  effort level, writing `reasoningDefaults`; a note that only synthesis is visible
  in chat and the others affect cost/latency/quality, and that levels above `off`
  are equivalent on Ollama (binary) and only graded on cloud providers.
- **Persistence:** zustand `persist` middleware (localStorage) on the
  `reasoningDefaults` slice only (not the session override).

## 6. Testing

- **Spike test (gates §4.2):** a level set in `SendMessageUseCase.execute` reaches a
  fake lane-aware adapter through `agent.run()` — proving contextvar propagation.
- Adapter: `_get_llm()` returns the env-default model when no override; returns the
  per-level model when the contextvar names its lane; caches per level (build called
  once per distinct level).
- Use case: sets the contextvar from `reasoning` and resets it in `finally`.
- DTO: `SendMessageRequest` accepts/omits `reasoning`; omitted = None.
- FE: typecheck; store selector computes the effective reasoning (override vs
  default precedence). Manual smoke: toggle in composer + settings → disclosure
  reflects it.

## 7. Scope / files

**Backend:** `interfaces/api/routes/chat_routes.py` (DTO + send handler),
`application/use_cases/chat_use_cases.py` (`execute` param + set contextvar),
new `infrastructure/llm/reasoning_context.py` (the ContextVar),
`infrastructure/llm/adapters/langchain_llm_client.py` (lane + per-level cache +
read contextvar), `infrastructure/llm/adapters/tool_calling_adapter.py` (same),
`infrastructure/di/container.py` (pass `lane` to each client), tests.

**Frontend:** `lib/stores/chat-store.ts`, `hooks/use-chat.ts`,
`components/chat/ChatInput.tsx`, new `components/chat/ReasoningSettings.tsx`,
`app/[workspace]/settings/page.tsx`, `packages/types` (request reasoning shape if
typed).

## 8. Risks / to confirm during implementation

- **#1 ContextVar propagation through the async-generator + SSE pipeline** — spike
  first (§6); threading fallback if it fails.
- Per-level model cache must key on the *resolved* level (post-fallback), so the
  env-default path stays a single cached model (no rebuild per request).
- Lane-aware construction must reach BOTH adapter types (`LangChainLLMClient` and
  the tool-calling adapter) — the container builds them in different places.
- **Batch isolation:** the non-chat batch client (`create_llm_client`, used by
  NER/summarization/pipeline workers) is also a `LangChainLLMClient`. It must be
  constructed with **`lane=None`** so it never consults the chat reasoning
  contextvar — `_get_llm()` only reads the override when `self._lane is not None`.
  This prevents a chat request's reasoning from bleeding into batch work that
  inherits the context. Only the three chat lane clients are tagged.
- `reasoning` reset in `finally` so a level cannot leak to a later request sharing
  the task (defensive; tasks are normally per-request).
- FE: localStorage persistence must not block first render (hydration); guard the
  persisted read.
