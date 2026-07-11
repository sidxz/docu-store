# NER Extraction Pipeline

## Overview

This document covers the integration of **structflo-ner** into the docu-store pipeline to
extract typed named entities from page text and store them as `TagMention` value objects
on the `Page` aggregate. Aggregated entity tags are then propagated to the parent `Artifact`.

The extracted tags become the foundation for the [Knowledge Graph](KNOWLEDGE_GRAPH.md)
(see that document for the long-term vision). This document covers the immediate
implementation: entity extraction, domain storage, and artifact-level aggregation.

---

## What structflo-ner Extracts

`structflo-ner` supports two extraction modes. We use **LLM-powered extraction** for
quality, with the domain profile set for pharmaceutical/biology:

| Entity Type    | Examples                                     |
|----------------|----------------------------------------------|
| `compound_name` | SACC-123, Rifampicin, ethionamide           |
| `target`       | NadD, InhA, KasA                             |
| `disease`      | tuberculosis, TB, MDR-TB                     |
| `gene`         | Rv3138, nadD                                 |
| `protein`      | NaMN adenylyltransferase, EthA               |
| `assay`        | MIC, MABA, LORA, enzymatic inhibition assay  |
| `bioactivity`  | IC50=2.3µM, MIC90=0.5µg/mL, CC50=18µM       |
| `mechanism`    | competitive inhibition, covalent binding     |
| `accession`    | P0A7D9, 3Q5Z, CHEMBL12345                   |

The `NERResult` from structflo-ner returns all entities as typed lists plus a flat
collection, exportable to JSON. We consume the flat collection.

---

## Domain Model Change: `TagMention.entity_type`

The current `TagMention` value object has only `tag: str` plus `ExtractionMetadata` fields.
To store entity type alongside the tag, we add one optional field:

```python
class TagMention(ExtractionMetadata):
    tag: str
    entity_type: str | None = None   # NEW: "compound_name", "target", "disease", etc.
```

This is backwards-compatible — existing generic tags (entity_type=None) remain valid.
The NER pipeline sets `entity_type` to the structflo-ner entity type string.
Generic tagging workflows that don't know entity type can leave it as `None`.

The `Artifact.TagsUpdated` event stores `list[str]` (plain strings) — no change needed
there. Artifact tags are aggregated, normalised strings; per-entity type metadata lives
only at the page level.

---

## Pipeline Trigger

NER runs **in parallel** with the existing text embedding workflow, both triggered by
`Page.TextMentionUpdated`. It does not depend on embeddings or summarization.

```
Page.TextMentionUpdated
  ├── (existing) TriggerTextEmbeddingUseCase
  │     → TextEmbeddingWorkflow → Page.TextEmbeddingGenerated → summarization
  │
  └── (new) TriggerNERExtractionUseCase
        → NERExtractionWorkflow
            → ExtractPageEntitiesActivity
                → structflo-ner on page.text_mention.text
                → Page.update_tag_mentions([TagMention(...)])
                → Page.TagMentionsUpdated
                    → TriggerArtifactTagAggregationUseCase
```

### Why parallel, not sequential?

- NER is independent of embedding quality — it operates on raw text.
- Adding it sequentially (after `TextEmbeddingGenerated`) would delay entity availability
  by the full embedding latency for no benefit.
- The only shared resource is the Page aggregate. The NER workflow writes `tag_mentions`;
  the embedding workflow writes `text_embedding_metadata`. These are different fields →
  no concurrency conflict.

---

## New Event: `Page.TagMentionsUpdated` (already exists)

No new domain event required. `Page.TagMentionsUpdated` already exists in the aggregate.
The pipeline worker only needs a new subscription to this event (for artifact aggregation).

---

## Artifact Tag Aggregation

After `Page.TagMentionsUpdated` fires, we aggregate all tags from all pages of the parent
artifact into `Artifact.tags` (via the existing `Artifact.TagsUpdated` event).

**Strategy:** collect all unique `tag` strings across all pages of the artifact, normalise
(lowercase strip), deduplicate, then call `artifact.update_tags(...)`.

This is a simple denormalised read / write-through pattern:

```
Page.TagMentionsUpdated
  → TriggerArtifactTagAggregationUseCase(page_id)
      1. page_repository.get(page_id)           # get artifact_id
      2. artifact_repository.get(artifact_id)   # get page list
      3. for page_id in artifact.pages:
             page = page_repository.get(page_id)
             collect page.tag_mentions[].tag
      4. normalise + deduplicate
      5. artifact.update_tags(aggregated_tags)  # fires Artifact.TagsUpdated
      6. artifact_repository.save(artifact)
```

Guard: if the artifact has many pages and not all have been NER-processed yet, the
aggregation still runs — it simply reflects whatever tags have been extracted so far.
Each subsequent `Page.TagMentionsUpdated` re-runs aggregation and refreshes the artifact.

---

## New Use Cases

### `ExtractPageEntitiesUseCase`

- Input: `page_id: UUID`
- Loads `Page` aggregate, reads `page.text_mention`
- Guard: skip if `text_mention is None` or `text_mention.text` is blank
- Calls `ner_extractor.extract(text)` → `NERResult`
- Maps `NERResult` flat entities to `list[TagMention]` with `entity_type` set
- Calls `page.update_tag_mentions(tag_mentions)`
- Saves page via `page_repository.save(page)`
- Returns `Result[dict, AppError]`

### `TriggerNERExtractionUseCase`

- Input: `page_id: UUID`
- Starts `NERExtractionWorkflow` via orchestrator
- Workflow ID: `ner-extraction-{page_id}`, `ALLOW_DUPLICATE` reuse
- Returns `WorkflowStartedResponse`

### `AggregateArtifactTagsUseCase`

- Input: `page_id: UUID`
- Loads page → gets `artifact_id`
- Loads artifact → gets `artifact.pages` list
- Loads each page's `tag_mentions`
- Flattens, deduplicates, normalises tags
- Calls `artifact.update_tags(aggregated_tags)`
- Saves artifact
- Returns `Result[dict, AppError]`

### `TriggerArtifactTagAggregationUseCase`

- Input: `page_id: UUID`
- Starts `ArtifactTagAggregationWorkflow` via orchestrator
- Workflow ID: `artifact-tag-aggregation-{artifact_id}`, `ALLOW_DUPLICATE`
  (uses artifact_id not page_id to avoid duplicate parallel runs per artifact)

---

## New Port: `NERExtractor`

```python
class NERExtractor(Protocol):
    async def extract(self, text: str) -> list[NEREntity]: ...

@dataclass
class NEREntity:
    text: str          # extracted entity string (e.g. "SACC-123", "NadD")
    entity_type: str   # "compound_name", "target", "disease", etc.
    confidence: float | None = None
```

The adapter wraps `structflo-ner`'s `LLMExtractor` (or `DictionaryExtractor` for fast mode).

---

## New Infrastructure Adapter: `StructfloNERExtractor`

```python
class StructfloNERExtractor:
    """Adapter wrapping structflo-ner for entity extraction."""

    def __init__(self, model: str = "ollama/gemma3:27b", profile: str = "tb"):
        # initialise structflo-ner LLMExtractor
        ...

    async def extract(self, text: str) -> list[NEREntity]:
        result = await asyncio.to_thread(self._extractor.extract, text)
        return self._map_to_ner_entities(result)

    def _map_to_ner_entities(self, result: NERResult) -> list[NEREntity]:
        entities = []
        for entity in result.entities:   # flat list from NERResult
            entities.append(NEREntity(
                text=entity.text,
                entity_type=entity.entity_type,
                confidence=entity.confidence,
            ))
        return entities
```

---

## Temporal Workflows & Activities

### `NERExtractionWorkflow`

```python
@workflow.defn(name="NERExtractionWorkflow")
class NERExtractionWorkflow:
    async def run(self, page_id: str) -> dict:
        # single activity: extract_ner_entities
        # schedule_to_close_timeout: 10 min (LLM call, slower than embedding)
        # retry: 3 attempts, 10s → 120s backoff
```

### `ArtifactTagAggregationWorkflow`

```python
@workflow.defn(name="ArtifactTagAggregationWorkflow")
class ArtifactTagAggregationWorkflow:
    async def run(self, artifact_id: str) -> dict:
        # single activity: aggregate_artifact_tags
        # schedule_to_close_timeout: 5 min
        # retry: 3 attempts, 5s → 60s backoff
```

Activities: `extract_ner_entities_activity`, `aggregate_artifact_tags_activity`.
Both follow the factory pattern from existing activities (injected use cases).

---

## Workflow Orchestrator Port additions

```python
async def start_ner_extraction_workflow(self, page_id: UUID) -> None: ...
async def start_artifact_tag_aggregation_workflow(self, artifact_id: UUID) -> None: ...
```

Workflow IDs:
- `ner-extraction-{page_id}`
- `artifact-tag-aggregation-{artifact_id}`

Both use `ALLOW_DUPLICATE` reuse policy — safe to re-trigger if text is re-extracted.

---

## Pipeline Worker additions

Two new subscriptions:

```
Page.TextMentionUpdated    → TriggerNERExtractionUseCase       (new, parallel)
Page.TagMentionsUpdated    → TriggerArtifactTagAggregationUseCase (new)
```

`Page.TextMentionUpdated` already triggers `TriggerTextEmbeddingUseCase`. Both use
cases now run independently — no shared state, no sequencing needed.

---

## Updated Full Event Pipeline

```
Artifact.Created
  └── ArtifactProcessingWorkflow (PDF parse → page creation)

Page.Created
  └── CompoundExtractionWorkflow (CSER)

Page.TextMentionUpdated
  ├── TriggerTextEmbeddingUseCase
  │     └── TextEmbeddingWorkflow
  │           └── Page.TextEmbeddingGenerated
  │                 └── TriggerSummarizationUseCase
  │                       └── SummarizationWorkflow
  │                             └── Page.SummaryCandidateUpdated
  │                                   ├── TriggerArtifactSummarizationUseCase
  │                                   └── TriggerPageSummaryEmbeddingUseCase
  │
  └── TriggerNERExtractionUseCase        ← NEW
        └── NERExtractionWorkflow
              └── Page.TagMentionsUpdated
                    └── TriggerArtifactTagAggregationUseCase  ← NEW
                          └── ArtifactTagAggregationWorkflow
                                └── Artifact.TagsUpdated

Page.CompoundMentionsUpdated
  └── TriggerSmilesEmbeddingUseCase

Page.SummaryCandidateUpdated
  ├── TriggerArtifactSummarizationUseCase
  └── TriggerPageSummaryEmbeddingUseCase

Artifact.SummaryCandidateUpdated
  └── TriggerArtifactSummaryEmbeddingUseCase
```

---

## Config additions

```python
# NER extractor settings
ner_model: str = Field(
    default="ollama/gemma3:27b",
    validation_alias="NER_MODEL",
)
ner_profile: str = Field(
    default="tb",
    validation_alias="NER_PROFILE",
    description="structflo-ner domain profile (e.g. 'tb' for tuberculosis)",
)
ner_mode: Literal["llm", "dictionary"] = Field(
    default="llm",
    validation_alias="NER_MODE",
    description="'llm' for quality, 'dictionary' for fast/deterministic",
)
```

---

## Files to create

| File | Role |
|------|------|
| `application/ports/ner_extractor.py` | `NERExtractor` Protocol + `NEREntity` dataclass |
| `application/use_cases/extract_page_entities_use_case.py` | `ExtractPageEntitiesUseCase` |
| `application/use_cases/aggregate_artifact_tags_use_case.py` | `AggregateArtifactTagsUseCase` |
| `application/workflow_use_cases/trigger_ner_extraction_use_case.py` | Start NER workflow |
| `application/workflow_use_cases/trigger_artifact_tag_aggregation_use_case.py` | Start aggregation workflow |
| `infrastructure/ner/structflo_ner_extractor.py` | Adapter wrapping structflo-ner |
| `infrastructure/temporal/workflows/ner_workflow.py` | `NERExtractionWorkflow`, `ArtifactTagAggregationWorkflow` |
| `infrastructure/temporal/activities/ner_activities.py` | Two activity factories |

## Files to modify

| File | Change |
|------|--------|
| `domain/value_objects/tag_mention.py` | Add `entity_type: str \| None = None` field |
| `application/ports/workflow_orchestrator.py` | Add `start_ner_extraction_workflow`, `start_artifact_tag_aggregation_workflow` |
| `infrastructure/temporal/orchestrator.py` | Implement 2 new `start_*` methods |
| `infrastructure/temporal/worker.py` | Register 2 workflows + 2 activities |
| `infrastructure/pipeline_worker.py` | Subscribe to `Page.TextMentionUpdated` (NER trigger) and `Page.TagMentionsUpdated` (aggregation trigger) |
| `infrastructure/config.py` | Add `ner_model`, `ner_profile`, `ner_mode` |
| `infrastructure/di/container.py` | Wire `NERExtractor` adapter + 4 new use cases |

---

## Implementation order

1. **Domain** — add `entity_type` to `TagMention`
2. **Config** — add NER settings
3. **Port** — `NERExtractor` Protocol + `NEREntity`
4. **Adapter** — `StructfloNERExtractor` wrapping structflo-ner
5. **Use cases** — `ExtractPageEntitiesUseCase`, `AggregateArtifactTagsUseCase`
6. **Trigger use cases** — `TriggerNERExtractionUseCase`, `TriggerArtifactTagAggregationUseCase`
7. **Temporal** — workflows + activities + register in worker
8. **Orchestrator** — add 2 new `start_*` methods
9. **Pipeline worker** — add 2 new subscriptions
10. **DI container** — wire everything

---

## Key design invariants

- **Parallel to embedding** — NER and text embedding run concurrently from `TextMentionUpdated`.
  No sequencing dependency between them.
- **No new domain events** — `Page.TagMentionsUpdated` already exists. `Artifact.TagsUpdated`
  already exists. No domain model changes beyond adding `entity_type` to `TagMention`.
- **Artifact tags are eventually consistent** — they reflect whatever pages have been
  NER-processed at the time of each aggregation run. Each new `Page.TagMentionsUpdated`
  refreshes the artifact. This is correct behaviour.
- **Idempotent** — re-triggering NER on the same page replaces `tag_mentions` entirely.
  Artifact aggregation is also a full replace. Both are safe to retry.
- **Extractor is swappable** — the `NERExtractor` port allows switching between LLM mode
  (quality, slower) and dictionary mode (fast, deterministic) without touching use cases.
- **entity_type is optional** — existing generic tag workflows set `entity_type=None`.
  NER workflows always set it. Query code can filter by `entity_type` or ignore it.
