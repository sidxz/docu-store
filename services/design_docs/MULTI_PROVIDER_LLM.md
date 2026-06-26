# Multi-Provider LLM Layer

**Status:** Approved design — pending implementation plan
**Date:** 2026-06-25
**Author:** sidx

## 1. Context

The LLM layer (`services/infrastructure/llm/`) is clean ports-and-adapters on
**LangChain 1.2.9**, but provider support has drifted:

- `OllamaLLMClient` and `OpenAILLMClient` are ~95% identical; the two
  tool-calling adapters (`NativeToolCallingAdapter`, `ReactToolCallingAdapter`)
  duplicate the same provider-branching `_get_llm`.
- `langchain-openai` is **not installed** — the OpenAI adapter would `ImportError`
  if selected.
- `config.py` advertises a `"gemini"` provider that `factory.py` rejects.
- Tool calling forces **ReAct text-parsing** for any non-OpenAI provider — a
  workaround from when Ollama lacked native function calling. Now obsolete.

Meanwhile the local-model story has changed (web-verified, June 2026):

- **Gemma 4** (Apr 2026): native function-calling, structured JSON output,
  vision/multimodal (PDF parsing, charts, OCR — directly relevant to a document
  store), 128K–256K context, built-in reasoning mode.
- **Ollama v0.30.8**: native + streaming tool calls, `reasoning`/`think` toggle,
  JSON-schema structured outputs.
- **LangChain `init_chat_model("<model>", model_provider=...)`** natively
  constructs `ollama` / `openai` / `anthropic` / `google_genai`.

## 2. Constraints

- **Confidentiality / air-gap (load-bearing):** some deployments forbid cloud
  LLMs. The **Ollama path must be fully capable and self-sufficient**, and the
  system must be able to **refuse** cloud providers outright. No silent fallback
  that could leak data to a third party.
- No behavior change for existing deployments (default stays Ollama).
- Stay on LangChain; do not add a competing abstraction (e.g. LiteLLM).

## 3. Goals / Non-goals

**Goals**
- One provider-agnostic LLM client; add Claude (Anthropic), finish Gemini, fix
  OpenAI, keep Ollama first-class.
- Unlock four capabilities uniformly: native tool calling, thinking/reasoning,
  structured outputs, vision/multimodal.
- Hard guard against cloud providers for confidential deployments.

**Non-goals**
- Embeddings (separate provider axis; Claude has no embedding API) — untouched.
- New chat UX surfaces beyond wiring reasoning into existing chat modes.

## 4. Design

### 4.1 Single generic adapter

Replace `OllamaLLMClient` + `OpenAILLMClient` with one `LangChainLLMClient`
wrapping a `BaseChatModel` produced by `init_chat_model`. Message-building and
image handling are already identical across today's adapters, so this is mostly
deletion.

A single `build_chat_model(...)` helper (new `llm/model_builder.py`) becomes the
**one** construction point — used by the LLM client *and* the tool-calling
adapter — removing the duplicated `_get_llm` branches. It owns: provider
selection, provider-specific kwargs (`base_url`, `api_key`, reasoning), and the
cloud guard (§4.4).

### 4.2 Provider matrix

| Provider | Package | Local/Cloud | Notes |
|---|---|---|---|
| `ollama` | `langchain-ollama` (installed) | Local | First-class; default |
| `openai` | `langchain-openai` (add) | Cloud | Fixes current ImportError |
| `anthropic` | `langchain-anthropic` (add) | Cloud | Claude — new |
| `gemini` | `langchain-google-genai` (add) | Cloud | Finishes half-wired literal |

### 4.3 Capability normalization

Uniform at the port, provider-specific inside `build_chat_model` / a small
per-provider kwargs builder:

| Capability | Ollama (local) | Claude | OpenAI | Gemini |
|---|---|---|---|---|
| Native tool calling | `bind_tools()` (Gemma 4/Qwen/Llama) | `bind_tools()` | `bind_tools()` | `bind_tools()` |
| Thinking/reasoning | `reasoning=True` → `additional_kwargs.reasoning_content` | `thinking={enabled, budget_tokens}`; newer Opus uses `{adaptive}` + effort | `reasoning_effort` (o-series/gpt-5) | thinking config |
| Structured output | `with_structured_output(schema)` (`json_schema` native) | same (`function_calling`) | same | same |
| Vision | content blocks (Gemma 4 multimodal) | content blocks | content blocks | content blocks |

- **Tool calling:** native is the default. `chat_agent_tool_calling_mode =
  "auto"` → native for **all** providers (Gemma 4 / modern Ollama models do
  native tools). `ReactToolCallingAdapter` is kept only as an explicit
  `"react"` opt-in for old local models that lack native tool support — no
  capability registry; operators set it when needed.
- **Structured output:** new port method `complete_structured(prompt, schema, ...)`.
  Default method `function_calling` (portable common denominator; Gemma 4
  supports it); `json_schema` available for Ollama-native.
- **Reasoning:** configured at construction from `llm_reasoning` /
  `chat_llm_reasoning`; `build_chat_model` translates the effort to
  provider-specific constructor kwargs (safe/documented, unlike per-call
  `.bind()`). Dynamic per-mode switching + streaming reasoning into the chat SSE
  is Phase 3 adoption. `complete`/`stream` signatures stay unchanged.
- **Vision:** already implemented via content blocks; this change makes it work
  for all providers rather than only the active one.

### 4.4 Config + confidentiality guard

`infrastructure/config.py`:
- Provider literals (batch + chat) → `Literal["ollama","openai","anthropic","gemini"]`.
- Keys: add `anthropic_api_key`, `google_api_key` (alongside `openai_api_key` /
  `llm_api_key`).
- Capability knobs: `llm_reasoning` / `chat_llm_reasoning` (`off|low|med|high`);
  reuse `chat_agent_tool_calling_mode`.
- **`ALLOW_CLOUD_LLM`** (default `true`): when `false`, `build_chat_model`
  hard-refuses any non-Ollama provider and raises at startup. Defense-in-depth so
  a misconfiguration cannot reach the internet from a confidential deployment.

### 4.5 Port changes

`application/ports/llm_client.py` (backward-compatible — one new method only):
- `+ complete_structured(prompt, schema, *, system_prompt=None) -> dict`

Reasoning needs no port change — it's configured at construction (§4.3), so
`complete`/`stream` signatures and all existing call sites are untouched.

## 5. File changes

**New**
- `infrastructure/llm/adapters/langchain_llm_client.py`
- `infrastructure/llm/model_builder.py` (`build_chat_model` + cloud guard)

**Delete**
- `infrastructure/llm/adapters/ollama_client.py`
- `infrastructure/llm/adapters/openai_client.py`

**Edit**
- `infrastructure/llm/adapters/tool_calling_adapter.py` — use shared builder;
  native default, ReAct fallback
- `infrastructure/llm/factory.py` — slimmed to delegate to `build_chat_model`
- `application/ports/llm_client.py` — `complete_structured`, `reasoning` kwarg
- `infrastructure/config.py` — literals, keys, reasoning knobs, `ALLOW_CLOUD_LLM`
- `pyproject.toml` — add `langchain-openai`, `langchain-anthropic`,
  `langchain-google-genai`

## 6. Phasing

1. **Core swap** — generic adapter + `model_builder` + factory + config + cloud
   guard; add cloud deps. Default stays Ollama → zero behavior change.
2. **Tool calling** — native default; ReAct demoted to fallback.
3. **Adoption** — wire reasoning into existing chat `thinking`/`deep_thinking`
   modes; migrate highest-value structured-output sites (NER, doc-metadata
   extraction) off text parsing.

## 7. Testing

- `build_chat_model` selects the right provider/class per config (mock
  `init_chat_model`).
- Cloud guard raises when `ALLOW_CLOUD_LLM=false` and a cloud provider is set.
- Adapter `complete` / `stream` / `complete_structured` / vision against a fake
  `BaseChatModel`.
- One integration smoke against local Ollama + Gemma 4 where available.

## 8. Risks / to confirm during implementation

- Exact reasoning kwargs in the installed `langchain-*` versions — ChatOllama
  `reasoning` had a known quirk (langchain issue #33041).
- `init_chat_model` passes `base_url` + provider kwargs cleanly for Ollama.
- Cloud package versions resolve against `langchain-core 1.2.9`.
- LangChain normalizes vision content blocks for Anthropic/Gemini.

## 9. Packaging note

Cloud packages are *installed* but never *contacted* unless selected (no network
at import) — acceptable for air-gapped installs. If installs must be lean, make
them optional extras instead; deferred unless requested.

## 10. Implementation status & handoff (2026-06-26)

**Branch:** `update-2` (commits `73b3034..4ce82ea`, ~13 ahead of `main`, kept
as-is — not pushed/merged). Suite green (349). New code lint-clean.

**Landed (Phases 1–2):** single `LangChainLLMClient` + `build_chat_model` (cloud
guard); factory rewired, old Ollama/OpenAI adapters deleted; providers
ollama/openai/anthropic/gemini; native tool calling default (ReAct = explicit
`react` opt-in); `complete_structured`; reasoning-at-construction; `ALLOW_CLOUD_LLM`
guard fails fast at factory; default model now `gemma4:31b`.

**Live-verified against `gemma4:31b`** (Ollama @ localhost:11434): `complete`,
`stream`, `complete_structured` (titled schema), native tool calling, `reasoning`
(no #33041 leak), and the cloud guard / fail-fast — all PASS.

**Remaining tasks (for a fresh session):**

1. ~~**`complete_structured` title fix**~~ **DONE.** Adapter now injects
   `{"title": "response", ...}` when a dict schema lacks a top-level title (fixes the
   `Unsupported function … must have a top-level 'title' key` ValueError). Covered by
   two unit tests (inject + preserve-existing) in `test_langchain_llm_client.py`.
2. **Phase 3 adoption** (needs brainstorm→spec→plan): drive `chat_llm_reasoning`
   from chat `quick`/`thinking`/`deep_thinking` modes + surface
   `additional_kwargs.reasoning_content` (currently dropped) into the SSE stream;
   migrate NER (`infrastructure/ner/`) + doc-metadata extraction to
   `complete_structured` (depends on #1).
3. **Deferred Minors** — full list in the SDD ledger `.superpowers/sdd/progress.md`:
   image MIME hardcoded `image/png` (cloud vision w/ non-PNG errors on
   Anthropic/Gemini); LLM errors not wrapped to `RuntimeError` per port docstrings;
   OpenAI builder missing `stream_usage=True` (stream usage logs zeros);
   `_BaseToolCallingAdapter` lacks `@abstractmethod`; `test_config_llm.py` no env
   isolation; `build_chat_model(allow_cloud=True)` fail-open default; assorted
   coverage gaps.
4. **Not yet live-tested:** the ReAct fallback path (`mode=react`, for gemma3/older);
   cloud-provider reasoning kwargs (Claude `thinking` / Gemini `thinking_budget` /
   OpenAI `reasoning_effort`) — no cloud keys were used. Note `langchain-core`
   resolved to **1.4.8**, not the 1.2.9 floor.
5. **Branch integration** — decide push+PR vs merge to `main`.
6. **Out of scope (flagged):** `evaluation/judge.py` builds cloud SDKs directly,
   ungoverned by `ALLOW_CLOUD_LLM` (offline harness; matters only for truly
   air-gapped installs).

**Pointers:** plan `docs/superpowers/plans/2026-06-25-multi-provider-llm.md`
(gitignored); SDD ledger `.superpowers/sdd/progress.md` (gitignored, per-task
status + minors).
