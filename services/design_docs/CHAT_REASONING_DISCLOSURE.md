# Chat Reasoning Disclosure — live model reasoning in the UI

**Status:** Approved design — pending implementation plan
**Date:** 2026-06-26
**Author:** sidx
**Related:** `MULTI_PROVIDER_LLM.md` §10 (this is the deferred "surface reasoning to UI" item)

## 1. Context

The multi-provider LLM work added native model reasoning (Ollama `reasoning=True`
→ `additional_kwargs.reasoning_content`; cloud equivalents) and per-lane config
(`CHAT_SYNTHESIS_REASONING` drives the thinking/deep_thinking answer-generation
client). But the model's reasoning is **dropped**: `LangChainLLMClient.stream()`
yields only `chunk.content` and discards `additional_kwargs.reasoning_content`.

Meanwhile the frontend already has a full "thinking" surface:
`AgentThinkingPanel.tsx` renders a collapsible "Agent thoughts" log fed by
`thinking_content` / `thinking_label` SSE events, accumulated into
`streamingThinkingBlocks` (Zustand) and persisted as `agent_trace.thinking_blocks`.
That panel shows the **agent's pipeline trace** (planning, retrieval, verification)
— application-level deliberation, not the model's internal chain-of-thought.

This feature surfaces the **model's** reasoning as a distinct, live, collapsible
"Reasoning" disclosure shown above the answer — separate from the agent-trace
panel.

## 2. Goal / Non-goals

**Goal:** In thinking/deep_thinking modes, stream the synthesis model's reasoning
tokens live into a dedicated collapsible "Reasoning" section above the answer, and
persist it so it survives conversation reload.

**Non-goals:**
- Quick mode reasoning surfacing (base client, reasoning off by default) — trivial
  follow-up, flagged in §7, not built in v1.
- Merging with or restyling the existing "Agent thoughts" trace panel.
- Cloud-provider live verification (no cloud keys; see `MULTI_PROVIDER_LLM.md` §10.4).

## 3. Key insight (why this is small)

`ThinkingAgent` already forwards **every** `("event", AgentEvent)` its synthesis
node yields, untouched, to the SSE stream (`thinking_agent.py:312-313`). So a new
`reasoning_token` event emitted by `AdaptiveSynthesisNode` reaches the client with
**no agent change**. The work concentrates in two places: the adapter seam (capture
reasoning from the stream) and the frontend (a new disclosure component).

## 4. Data flow

Ollama emits reasoning *before* the answer. During synthesis the reasoning streams
live to the FE; the answer streams later during the formatting stage. Result: the
disclosure fills with reasoning, then the answer appears below it.

```
synthesis client → stream_with_reasoning()
      ├─ ("reasoning", δ) → AgentEvent(type="reasoning_token", delta=δ) ─┐
      └─ ("content",   δ) → draft answer (accumulated internally, as today)
                                                                          │
AdaptiveSynthesisNode → ThinkingAgent (forwards events as-is) → SSE "reasoning_token" → FE
                                                                          │
                                          chat-store.appendReasoning(δ) → ReasoningDisclosure
```

The answer the user reads is produced by the **formatting** stage
(`AnswerFormattingNode`, base client, reasoning off), so no reasoning interleaves
with answer tokens. Clean separation: reasoning (synthesis) then answer (formatting).

## 5. Design

### 5.1 Adapter seam (the core)

New port method on `LLMClientPort` (backward-compatible addition):

```python
async def stream_with_reasoning(
    self, prompt, *, system_prompt=None, temperature=None, images_b64=None,
) -> AsyncGenerator[tuple[Literal["content", "reasoning"], str], None]
```

`LangChainLLMClient` implements it: for each streamed chunk, emit
`("reasoning", …)` for `chunk.additional_kwargs["reasoning_content"]` deltas and
`("content", …)` for `chunk.content`. The existing `stream()` becomes a thin
filter that delegates and yields only `"content"` text — so its two callers
(`AnswerFormattingNode`, `AnswerSynthesisNode`) are unchanged, and usage recording
stays in one place.

**`<think>`-tag fallback:** some local models inline reasoning as `<think>…</think>`
in `content` rather than a separate field (the langchain-ollama #33041 quirk). The
adapter encapsulates a small stateful segmenter so that, whichever shape the
installed stack produces, consumers only ever see `("reasoning"|"content", str)`
deltas. The exact shape is **spiked first** during implementation (see §8).

Mock LLM clients in `tests/mocks.py` gain the method.

### 5.2 Node + event

`AdaptiveSynthesisNode` switches its synthesis loop from `stream()` to
`stream_with_reasoning()`:
- `"reasoning"` delta → `yield ("event", AgentEvent(type="reasoning_token", delta=δ))`
- `"content"` delta → `yield ("token", δ)` (unchanged; accumulated into the draft)

`AgentEvent` gains `"reasoning_token"` in its `type` Literal and reuses the existing
`delta` field — no new event field. `chat_routes._map_event_type` maps
`reasoning_token` → `reasoning_token`.

### 5.3 Persistence

`AgentTraceDTO` gains `reasoning_content: str | None`. The send-message use case
(`chat_use_cases.py`) accumulates streamed `reasoning_token` deltas and stores the
concatenation on the saved assistant message's `agent_trace`. The chat read
repository must carry the new field through serialization (verify during build).
Persisted messages then render reasoning on reload.

### 5.4 Frontend

- **Types** (`packages/types/chat.ts`): add `"reasoning_token"` to `AgentEvent`;
  `reasoning_content?: string` on `AgentTrace`.
- **Store** (`chat-store.ts`): `streamingReasoning: string`, `appendReasoning(δ)`,
  reset on new message.
- **Stream hook** (`use-chat.ts`): handle `reasoning_token` → `appendReasoning`.
- **`ReasoningDisclosure.tsx`** (new): collapsible "Reasoning" section; markdown
  body; live "thinking…" indicator while streaming; auto-open while streaming,
  default-collapsed once the answer is present.
- **`ChatMessage.tsx`**: render the disclosure **above** the answer content — from
  `streamingReasoning` while streaming, `agent_trace.reasoning_content` when
  persisted.
- **`MessageList.tsx`**: thread `streamingReasoning` into the optimistic streaming
  assistant message.

Labeled **"Reasoning"** (model CoT), kept visually distinct from the existing
**"Agent thoughts"** trace panel.

## 6. Testing

- Adapter: `stream_with_reasoning` tags reasoning vs content from fake chunks with
  `additional_kwargs`; the `<think>`-tag fallback segments correctly; `stream()`
  still yields content-only.
- Node: `AdaptiveSynthesisNode` emits `reasoning_token` events for reasoning deltas.
- Mock updated; existing chat tests stay green.
- FE: a store unit test for `appendReasoning`; component render verified manually.

## 7. Scope & follow-ups

- **v1 = thinking/deep_thinking only.** Quick-mode reasoning surfacing is a trivial
  follow-up: use `stream_with_reasoning` in `AnswerSynthesisNode` and forward the
  event in `ChatAgent`.
- deep_thinking shares thinking's nodes (per `MULTI_PROVIDER_LLM.md`) — both surface
  reasoning identically.

## 8. Risks / to confirm during implementation

- **Ollama stream reasoning shape (#1 risk):** whether `langchain-ollama` exposes
  reasoning as `additional_kwargs.reasoning_content` deltas, a single end-of-stream
  field, or inline `<think>` tags. Spike a one-off `astream` against `gemma4:31b`
  before wiring the node; the adapter absorbs whichever shape it is.
- Read-model serialization must carry `agent_trace.reasoning_content` end to end.
- Generated FE OpenAPI types: regenerate if the chat DTOs are part of the typed
  client (the hand-written `packages/types/chat.ts` may be separate — confirm).

## 9. File summary

**Backend:** `application/ports/llm_client.py`,
`infrastructure/llm/adapters/langchain_llm_client.py`, `tests/mocks.py`,
`infrastructure/chat/nodes/adaptive_synthesis.py`,
`application/dtos/chat_dtos.py` (AgentEvent + AgentTraceDTO),
`interfaces/api/routes/chat_routes.py`, `application/use_cases/chat_use_cases.py`,
chat read repository (+ tests).

**Frontend:** `packages/types/src/domain/chat.ts`,
`apps/portal/src/lib/stores/chat-store.ts`, `apps/portal/src/hooks/use-chat.ts`,
`apps/portal/src/components/chat/ReasoningDisclosure.tsx` (new),
`apps/portal/src/components/chat/ChatMessage.tsx`,
`apps/portal/src/components/chat/MessageList.tsx`.
