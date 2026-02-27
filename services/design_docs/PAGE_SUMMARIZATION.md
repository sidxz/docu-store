# Page Summarization Feature

## What it does

Generates a natural-language summary for each `Page` aggregate using an LLM. Supports three
summarization modes selected automatically based on page content:

| Mode | Condition | LLM call |
|------|-----------|----------|
| **Hybrid** | `text_mention.text` ≥ 100 chars | text prompt + page image (multimodal) |
| **Image-only** | text < 100 chars, image exists in blob store | page image only (multimodal) |
| **Text-only** | no image available | text prompt only |

Results are persisted as a `SummaryCandidate` value object on the `Page` aggregate (field
already exists). Artifact-level (document) summary is **out of scope for this iteration**
and will be implemented separately.

---

## Prerequisite: Persist Page Images

Page images are currently extracted in memory during the upload saga but **never written to
blob storage**. This must be fixed before multimodal summarization can work.

**Change**: `application/sagas/artifact_upload_saga.py` — after creating each page, write
its PNG (already available in `PDFContent.pages_png`) to blob store:

```
key pattern:  artifacts/{artifact_id}/pages/{page_index}.png
mime type:    image/png
```

No domain model change is required. The summarization use case reconstructs this key
deterministically from `page.artifact_id` + `page.index`.

---

## Trigger points

| Trigger | Event / Entry | Path |
|---------|---------------|------|
| Automatic | `Page.TextMentionUpdated` → EventStoreDB | `pipeline_worker.py` → `TriggerPageSummarizationUseCase` → Temporal |
| Manual | `POST /pages/{page_id}/summarize` | API → `TriggerPageSummarizationUseCase` → Temporal |

Both paths converge at the same Temporal workflow. Re-triggering is safe — the Temporal
workflow ID `page-summarization-{page_id}` provides idempotency. Re-triggering via the API
will start a **new** summarization run (useful when prompts are updated in Langfuse).

For the automatic trigger: `TextMentionUpdated` fires every time text is re-extracted.
`TriggerPageSummarizationUseCase` does **not** guard against re-runs — every
`TextMentionUpdated` starts a new summarization. This is intentional: updated text should
produce a fresh summary.

---

## Architecture: Two-Layer Design

This feature introduces **two distinct layers** that must be built separately.

### Layer 1 — Shared LLM Infrastructure
Provider-agnostic LLM capability reusable by all future features (Q&A, property prediction,
etc.). No knowledge of summarization specifics.

### Layer 2 — Summarization Feature
First consumer of Layer 1. Follows the compound extraction pattern exactly.

---

## Layer 1: Shared LLM Infrastructure

### New Ports

**`application/ports/llm_client.py`**
```python
class LLMClientPort(Protocol):
    async def complete(
        self, prompt: str, *, system_prompt: str | None = None, temperature: float = 0.1
    ) -> str: ...

    async def complete_with_image(
        self, prompt: str, image_b64: str, *, system_prompt: str | None = None
    ) -> str: ...

    async def get_model_info(self) -> dict[str, str]: ...
```

**`application/ports/prompt_repository.py`**
```python
@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    template_str: str          # Jinja2 / f-string style, e.g. "Summarise: {slide_text}"
    input_variables: list[str]

class PromptRepositoryPort(Protocol):
    async def get_prompt(self, name: str, version: str | None = None) -> PromptTemplate: ...
```

`PromptTemplate` is a plain application-layer value object. No LangChain or Langfuse types
leak into the application layer.

### Infrastructure: `infrastructure/llm/`

```
infrastructure/llm/
  adapters/
    ollama_client.py          ← primary; implements LLMClientPort (LangChain ChatOllama)
    openai_client.py          ← future; stub implementing same protocol
    gemini_client.py          ← future; stub implementing same protocol
  prompt_repositories/
    langfuse_prompt_repository.py   ← primary; fetches versioned prompts from Langfuse
    yaml_prompt_repository.py       ← offline fallback (dev without Langfuse running)
  default_prompts/
    page_summarization_hybrid.yaml
    page_summarization_image_only.yaml
    page_summarization_text_only.yaml
  factory.py    ← create_llm_client(settings) -> LLMClientPort
                   create_prompt_repository(settings) -> PromptRepositoryPort
```

**Ollama multimodal**: Uses LangChain `ChatOllama` with `HumanMessage` image content (no
raw `ollama` SDK needed). Lazy import — no top-level imports.

**Langfuse**: The SDK patches the LangChain callback chain automatically, so every LLM call
is traced (tokens, latency, cost) without any application code change. Prompts are versioned
in the Langfuse UI. The adapter fetches the latest compiled prompt unless a version is
pinned via config.

**YAML fallback**: `yaml_prompt_repository.py` reads from `default_prompts/`. Use during
development when Langfuse is not running (`PROMPT_REPOSITORY_TYPE=yaml`).

### New Config (add to `infrastructure/config.py`)

```python
# LLM provider
llm_provider: Literal["ollama", "openai", "gemini"] = "ollama"
llm_model_name: str = "gemma3:27b"
llm_base_url: str = "http://localhost:11434"   # Ollama; ignored for cloud providers
llm_api_key: str | None = None                 # OpenAI / Gemini key
llm_temperature: float = 0.1                   # Low for deterministic summaries

# Prompt management
prompt_repository_type: Literal["langfuse", "yaml"] = "langfuse"
langfuse_host: str = "http://localhost:3000"
langfuse_public_key: str | None = None
langfuse_secret_key: str | None = None
```

---

## Layer 2: Summarization Feature

### Data flow

```
Page.TextMentionUpdated (EventStoreDB)  OR  POST /pages/{page_id}/summarize
  → TriggerPageSummarizationUseCase
      → page.update_workflow_status(PAGE_SUMMARIZATION_WORKFLOW, in_progress)
      → page_repository.save(page)
      → WorkflowOrchestrator.start_page_summarization_workflow(page_id)

Temporal: PageSummarizationWorkflow  [15 min timeout, 3 retries]
  → Activity: summarize_page_activity(page_id)
      → SummarizePageUseCase
          1. page_repository.get(page_id)  → Page (has artifact_id, index, text_mention)
          2. Determine mode:
               text ≥ 100 chars  → HYBRID
               text < 100 chars + image in blob store  → IMAGE_ONLY
               else  → TEXT_ONLY
          3. prompt_repository.get_prompt(f"page_summarization_{mode.lower()}")
          4. Render template: {slide_text}, {artifact_title}, {page_index}
          5. If HYBRID/IMAGE_ONLY: blob_store.get_bytes("artifacts/{id}/pages/{idx}.png")
                                   encode to base64
          6. LLMClientPort.complete() or .complete_with_image()
          7. llm_client.get_model_info() → model_name
          8. Create SummaryCandidate(
               summary=result,
               model_name=model_name,
               date_extracted=datetime.now(UTC),
             )
          9. page.update_summary_candidate(candidate)
         10. page.update_workflow_status(PAGE_SUMMARIZATION_WORKFLOW, completed)
         11. page_repository.save(page)
         12. external_event_publisher.notify_page_updated(page_id, artifact_id)
```

### Prompt names (registered in Langfuse, also in YAML fallback)

| Prompt name | Mode | Template variables |
|-------------|------|-------------------|
| `page_summarization_hybrid` | text + image | `{slide_text}`, `{artifact_title}`, `{page_index}` |
| `page_summarization_image_only` | image only | `{artifact_title}`, `{page_index}` |
| `page_summarization_text_only` | text only | `{slide_text}`, `{artifact_title}`, `{page_index}` |

---

## Files added

| File | Role |
|------|------|
| `application/ports/llm_client.py` | `LLMClientPort` Protocol |
| `application/ports/prompt_repository.py` | `PromptRepositoryPort` Protocol + `PromptTemplate` value object |
| `application/dtos/summarization_dtos.py` | `PageSummarizationResponse` DTO |
| `application/use_cases/summarization_use_cases.py` | `SummarizePageUseCase` |
| `application/workflow_use_cases/trigger_page_summarization_use_case.py` | `TriggerPageSummarizationUseCase` |
| `infrastructure/llm/adapters/ollama_client.py` | `OllamaLLMClient` (primary LLM adapter) |
| `infrastructure/llm/adapters/openai_client.py` | `OpenAILLMClient` (stub, future) |
| `infrastructure/llm/adapters/gemini_client.py` | `GeminiLLMClient` (stub, future) |
| `infrastructure/llm/prompt_repositories/langfuse_prompt_repository.py` | Langfuse adapter |
| `infrastructure/llm/prompt_repositories/yaml_prompt_repository.py` | YAML fallback |
| `infrastructure/llm/default_prompts/page_summarization_hybrid.yaml` | Default hybrid prompt |
| `infrastructure/llm/default_prompts/page_summarization_image_only.yaml` | Default image-only prompt |
| `infrastructure/llm/default_prompts/page_summarization_text_only.yaml` | Default text-only prompt |
| `infrastructure/llm/factory.py` | `create_llm_client()`, `create_prompt_repository()` |
| `infrastructure/temporal/workflows/summarization_workflow.py` | `PageSummarizationWorkflow` + `summarize_page_activity` |

## Files modified

| File | Change |
|------|--------|
| `application/sagas/artifact_upload_saga.py` | Persist page PNGs to blob store (prerequisite) |
| `application/dtos/workflow_dtos.py` | Add `PAGE_SUMMARIZATION_WORKFLOW` to `WorkflowNames` |
| `application/ports/workflow_orchestrator.py` | Add `start_page_summarization_workflow` method |
| `infrastructure/temporal/orchestrator.py` | Implement `start_page_summarization_workflow` (`workflow_id = f"page-summarization-{page_id}"`) |
| `infrastructure/temporal/worker.py` | Register `PageSummarizationWorkflow` + activity |
| `infrastructure/config.py` | Add LLM + Langfuse settings |
| `infrastructure/di/container.py` | Wire `LLMClientPort`, `PromptRepositoryPort`, `SummarizePageUseCase`, `TriggerPageSummarizationUseCase` |
| `infrastructure/pipeline_worker.py` | Add `Page.TextMentionUpdated` topic + handler |
| `interfaces/api/routes/page_routes.py` | Add `POST /pages/{page_id}/summarize` (202) and `GET /pages/{page_id}/summary` |

---

## Implementation order

1. **Prereq** — persist page PNGs in `artifact_upload_saga.py`
2. **Config** — add LLM + Langfuse vars to `infrastructure/config.py`
3. **Ports** — `llm_client.py`, `prompt_repository.py`
4. **DTOs + WorkflowNames** — `summarization_dtos.py`, add to `workflow_dtos.py`
5. **YAML prompts** — write the three default YAML prompt files
6. **LLM infrastructure** — `ollama_client.py`, `yaml_prompt_repository.py`, `langfuse_prompt_repository.py`, `factory.py`
7. **Core use cases** — `SummarizePageUseCase`, `TriggerPageSummarizationUseCase`
8. **Temporal workflow** — `summarization_workflow.py` (workflow + activity)
9. **Orchestrator + worker** — add new method + register workflow
10. **DI container** — wire everything
11. **Pipeline worker** — add `TextMentionUpdated` handler
12. **API routes** — trigger + read endpoints

---

## Notes

- LLM calls are slow (5–30 s). Always run via Temporal, never inline in the API.
- All LLM adapters must lazy-import their libraries to avoid startup cost in processes that
  don't need them (e.g. `read_worker`).
- Workflow ID `page-summarization-{page_id}` ensures idempotency for automatic triggers.
  Manual API re-trigger calls the use case directly which starts a new Temporal run.
- `SummaryCandidate.is_locked = True` means a human has manually corrected the summary —
  the use case must check this flag and skip re-summarization when locked.
- The mode-selection threshold (100 chars) mirrors the POC in `DocMLx-api`. Adjust via
  config if needed.
- Langfuse self-hosted requires a Postgres + Clickhouse backing store. Add to
  `docker-compose.yml`. Langfuse SDK version ≥ 3.x uses the new tracing API.
- Future: artifact-level summary (document executive summary) will follow the same pattern,
  consuming per-page `SummaryCandidate` values as input context with a sliding window.
