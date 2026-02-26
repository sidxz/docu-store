# Compound Extraction Feature

## What it does
Uses the `structflo-cser` ML library (YOLO detector + neural matcher + DECIMER SMILES extractor) to identify chemical structure-label pairs in PDF page images and persist them as `CompoundMention` value objects on the `Page` aggregate.

## Trigger points

| Trigger | Event | Handler |
|---------|-------|---------|
| Automatic | `Page.Created` → EventStoreDB | `pipeline_worker.py` starts Temporal workflow |
| Manual | `POST /pages/{page_id}/compounds/extract` | API → `TriggerCompoundExtractionUseCase` → Temporal |

Both paths converge at the same Temporal workflow.

## Data flow

```
Page.Created (EventStoreDB)
  → pipeline_worker.py
    → TriggerCompoundExtractionUseCase
      → page.update_workflow_status(COMPOUND_EXTRACTION_WORKFLOW, in_progress)
      → WorkflowOrchestrator.start_compound_extraction_workflow(page_id)

Temporal: ExtractCompoundMentionsWorkflow  [10 min timeout, 3 retries]
  → Activity: extract_compound_mentions(page_id)
    → ExtractCompoundMentionsUseCase
        1. page_repository.get(page_id)          → Page (has artifact_id, index)
        2. artifact_repository.get(artifact_id)  → Artifact (has storage_location)
        3. CserService.extract_compounds_from_pdf_page(storage_location, index)
             → blob_store.get_file() → local PDF path
             → fitz.open(pdf)[index].get_pixmap() → PIL Image (2× zoom)
             → ChemPipeline.process(image) → list[CompoundPair]
             → map to list[CserCompoundResult]
        4. Filter pairs where smiles is None
        5. Map CserCompoundResult → CompoundMention
             smiles            → smiles
             label_text        → extracted_id
             match_confidence  → confidence
             datetime.now(UTC) → date_extracted
             "structflo-cser"  → model_name
        6. page.update_compound_mentions(compound_mentions)
        7. page_repository.save(page)
        8. external_event_publisher.notify_page_updated(...)
```

## Files added

| File | Role |
|------|------|
| `application/dtos/cser_dtos.py` | `CserCompoundResult` — raw port output DTO |
| `application/ports/cser_service.py` | `CserService` Protocol port |
| `application/use_cases/compound_use_cases.py` | `ExtractCompoundMentionsUseCase` |
| `application/workflow_use_cases/trigger_compound_extraction_use_case.py` | `TriggerCompoundExtractionUseCase` |
| `infrastructure/cser/cser_pipeline_service.py` | `CserPipelineService` (lazy-loads `ChemPipeline`) |
| `infrastructure/temporal/workflows/compound_workflow.py` | `ExtractCompoundMentionsWorkflow` |
| `infrastructure/temporal/activities/compound_activities.py` | `extract_compound_mentions` activity |

## Files modified

| File | Change |
|------|--------|
| `application/dtos/workflow_dtos.py` | Added `COMPOUND_EXTRACTION_WORKFLOW` to `WorkflowNames` |
| `application/ports/workflow_orchestrator.py` | Added `start_compound_extraction_workflow` method |
| `infrastructure/temporal/orchestrator.py` | Implemented the new method (`workflow_id = f"compound-extraction-{page_id}"`) |
| `infrastructure/temporal/worker.py` | Registered `ExtractCompoundMentionsWorkflow` + activity |
| `infrastructure/di/container.py` | Wired `CserService`, `ExtractCompoundMentionsUseCase`, `TriggerCompoundExtractionUseCase` |
| `infrastructure/pipeline_worker.py` | Added `Page.Created` topic + handler |
| `interfaces/api/routes/page_routes.py` | Added `POST /pages/{page_id}/compounds/extract` (202) |

## Notes
- `ChemPipeline` is synchronous and slow — always run via Temporal, never inline in the API.
- The library is lazy-loaded in `CserPipelineService._ensure_pipeline_loaded()` to avoid paying startup cost until the first extraction.
- Workflow ID `compound-extraction-{page_id}` ensures idempotency (re-triggering won't duplicate).
- Pairs without a SMILES string are silently dropped — `CompoundMention.smiles` is required.
