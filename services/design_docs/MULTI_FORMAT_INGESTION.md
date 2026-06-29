# Multi-Format Ingestion & Document Parsing Redesign

**Status:** Design / proposed
**Date:** 2026-06-29
**Author:** Siddhant Rath (`sidx`)
**Scope:** Backend (`services/`) ingestion path only. Downstream extraction pipeline unchanged.

---

## 1. Why

The project exists to do **information extraction from scientific documents + RAG retrieval**.
Today it only ingests PDFs, and the ingestion path is the weakest part of an otherwise
solid system. Two problems:

1. **The front door is convoluted and synchronous.** `ArtifactUploadSaga.execute()`
   parses the entire PDF *inside the HTTP request* — opens the file, extracts text,
   renders every page to a 300-DPI PNG + thumbnail, creates page aggregates — all
   before returning `201`. Large PDFs hang the request. Parsing is not durable or
   retryable. (`application/sagas/artifact_upload_saga.py:90-145`)

2. **Everything is hardcoded to PDF.** MIME validation rejects anything but
   `application/pdf` (`application/use_cases/blob_use_cases.py:30`), even though the
   `MimeType` enum already lists `DOCX`/`PPTX`/`DOC`. The only parser is PyMuPDF, wired
   directly in DI with no dispatch (`container.py` ~line 321). The `Page` aggregate
   conflates "physical PDF page" with "unit of processing".

Notably, the **extraction pipeline behind ingestion is already format-agnostic and
well-built** (13 Temporal workflows; NER, embeddings, chunking, SMILES detection,
summarization all operate on text + images, not on "PDF"). The fix is therefore
**localized to ingestion** — we do not touch the downstream pipeline.

There is even dead evidence of the intended design: `ProcessArtifactWorkflow`
(`infrastructure/temporal/workflows/artifact_processing.py`) is a toy that only logs the
MIME type, with comments stating it *"will be expanded to include PDF parsing, page
extraction, LLM summarization, domain event emission"*. That expansion never happened.
This redesign builds it.

## 2. Goals / non-goals

**Goals**
- Ingest PDF, PPTX, DOCX, and HTML/article formats through one clean path.
- Make parsing **asynchronous, durable, and retryable** (Temporal), so upload returns instantly.
- Preserve document **structure** (reading order, multi-column, tables, headings, figures)
  instead of flattening to a jumbled string on ingest, as happens today.
- Improve extraction quality with **zero downstream churn** (the "(A)" tier below).

**Non-goals (explicitly deferred — the "(B)" tier)**
- First-class structured table/figure *objects* in retrieval and chat (cell-level table
  search, table/figure rendering as distinct UI elements, per-figure VLM understanding,
  citation graph). These require new aggregate fields, new Qdrant payload/point types, new
  search paths, and chat/UI work. We **retain the structure in the parsed-IR blob** so this
  stays open, but we do not build the consuming side until it's needed.
- Renaming the `Page` aggregate or its events (no event-store migration).
- A generic parser plugin framework (a MIME→parser dict is enough).
- Converting documents to any single *file* format (lossy — the thing we're avoiding).

## 3. Key decisions (settled during design)

| Decision | Choice | Rationale |
|---|---|---|
| Strategy | Targeted core fix in service of extraction quality | The mess is localized; extraction quality requires the fix |
| Parser | **Docling** (IBM, open-source, local) as default | One library → structured doc for PDF/DOCX/PPTX/HTML; deletes per-format parser code; local-first |
| Common representation | A neutral **`ParsedDocument` IR**, mapped from Docling | Downstream never imports Docling; a non-Docling parser can target the same IR later |
| Page model | **Redefine `Page` in place** (keep aggregate + events) | Zero event migration; "Page" becomes "unit of processing" |
| Page images | **Keep full-page renders** for every format we run CSER/chat on | Hard requirement — CSER's YOLO detector localizes structures on the *whole page*; chat uses page images as references |
| Tables/figures | **(A) now** (cleaner text + retain IR), **(B) deferred** | Don't extract structure the downstream can't consume yet |

## 4. Target architecture

### 4.1 New ingestion flow

```
POST /artifacts/upload
  └─ ArtifactUploadSaga (thinned):
       1. UploadBlobUseCase        — store blob; validate MIME ∈ supported set (not PDF-only)
       2. CreateArtifactUseCase    — emits Artifact.Created (storage_location + mime_type)
       3. register_resource        — Sentinel permissions
       └─ return ArtifactResponse immediately (pages=[], not yet parsed)   ← no parsing here

Artifact.Created  (pipeline_worker subscription)
  └─ TriggerArtifactParseUseCase → start ParseArtifactWorkflow(artifact_id, storage_location, mime_type)
       (workflow_id = f"parse-{artifact_id}", dedup reuse policy)

ParseArtifactWorkflow
  └─ activity: parse_artifact → ParseArtifactUseCase:
       1. parser = registry[mime_type]                    — DocumentParser dispatch
       2. parsed = parser.parse(blob_key)                 — Docling → ParsedDocument IR
       3. blob_store.put(artifacts/{id}/parsed/document.json, parsed)   — retain structure
       4. segments = Segmenter(mime_type).segment(parsed) — per-format unit of processing
       5. for each segment (idempotent, deterministic IDs):
            - create Page                → Page.Created
            - persist full-page image    → artifacts/{id}/pages/{index}.png (+ _thumb.jpg)
            - set text from segment      → Page.TextMentionUpdated
       6. AddPagesUseCase               → Artifact.PagesAdded
       7. (optional) Artifact.Parsed marker event

  └─ EXISTING pipeline takes over, UNCHANGED:
       Page.Created → compound extraction; Page.TextMentionUpdated → summary + NER + metadata; …
```

The critical invariant: **`Page.Created` and `Page.TextMentionUpdated` still fire**, now
emitted from the parse use case instead of the saga. Everything subscribed in
`infrastructure/pipeline_worker.py` works without modification.

### 4.2 Components

| # | Component | Location | Notes |
|---|---|---|---|
| 1 | `DocumentParser` port | `application/ports/document_parser.py` | `parse(blob_key, mime_type) -> ParsedDocument`. Generalizes existing `application/ports/pdf_service.py`. |
| 2 | `ParsedDocument` IR | `application/dtos/parsed_document.py` | Mirrors location of existing `pdf_dtos.PDFContent`. Pydantic, JSON-serializable. See §4.3. |
| 3 | `DoclingParser` | `infrastructure/file_services/docling_parser.py` | Wraps Docling `DocumentConverter`; maps `DoclingDocument` → `ParsedDocument`. |
| 4 | Parser registry | `infrastructure/di/container.py` | `dict[MimeType, DocumentParser]`. Phase 0: all → `DoclingParser`. |
| 5 | `Segmenter` | `infrastructure/file_services/segmenter.py` | Per-format strategy → list of segments. See §4.4. |
| 6 | `ParseArtifactWorkflow` | `infrastructure/temporal/workflows/artifact_processing.py` | Rename/rebuild of dead `ProcessArtifactWorkflow`. |
| 7 | `parse_artifact` activity | `infrastructure/temporal/activities/parse_activities.py` | Thin wrapper calling `ParseArtifactUseCase` (factory/injected pattern like other activities). |
| 8 | `ParseArtifactUseCase` | `application/use_cases/parse_artifact_use_case.py` | Orchestrates parser → IR blob → segmenter → pages → text → add-pages. |
| 9 | `TriggerArtifactParseUseCase` | `application/workflow_use_cases/` | Replaces the no-op `LogArtifactSampleUseCase` on `Artifact.Created`. |
| 10 | Thinned `ArtifactUploadSaga` | `application/sagas/artifact_upload_saga.py` | Drops parse + `_process_pdf_pages`. |
| 11 | Relaxed MIME validation | `application/use_cases/blob_use_cases.py:30` | Accept supported set, not PDF-only. |
| 12 | LibreOffice page renderer | `infrastructure/file_services/` | **Phase 2** — DOCX/HTML → PDF → page PNGs (for CSER + chat images). |
| 13 | Structure-aware chunker | `infrastructure/text_chunkers/` | **Phase 3** — chunk on IR section boundaries. |

### 4.3 The `ParsedDocument` IR

A neutral, serializable representation — a *superset* container, not a
lowest-common-denominator. Each format's parser maps into it, keeping what that format
uniquely offers.

```
ParsedDocument
  source_mime: str
  blocks: list[Block]                 # ordered, in reading order
  page_images: list[PageImage]        # full-page/slide renders, keyed by physical index

Block (tagged union):
  Heading(level, text)
  Paragraph(text)
  ListBlock(items)
  Table(rows: list[list[str]], caption)        # structured, retained for (B); linearized to markdown for (A)
  Figure(image_ref, caption)
  Equation(text)
  Code(text)
  Reference(text)
  Footnote(text)
  — each Block carries provenance: { source_page_index, bbox? }

PageImage:
  index: int          # physical page (PDF) / slide (PPTX) ordinal
  image_ref: str      # blob key
```

For the **(A)** tier, blocks are linearized to clean text/markdown (tables → markdown
tables) per segment and fed to the existing pipeline. The full structured `ParsedDocument`
is persisted as a blob so **(B)** can consume it later without re-parsing.

### 4.4 Segmentation — `Page` as "unit of processing"

The `Page` aggregate and its events are unchanged. Its *semantics* generalize from
"physical PDF page" to "unit of processing/retrieval". A per-format `Segmenter` produces
the segments:

| Format | One `Page` per… | Full-page image |
|---|---|---|
| PDF | physical page (parity with today) | Docling/PyMuPDF page render |
| PPTX | slide | slide render |
| DOCX / HTML / article | top-level **section** from heading hierarchy; sub-window if a section is very large; sliding window if no headings | LibreOffice → PDF → page render (Phase 2) |

`Page.index` remains the segment ordinal. Storage keys
(`artifacts/{id}/pages/{index}.png`) generalize unchanged. The page image is now
*optional in the model* but present for every format we actually use.

### 4.5 CSER and images (corrected)

CSER must receive the **full page image, not a crop** — its pipeline runs a YOLO detector
over the whole page to *locate* chemical structures before extracting SMILES
(`infrastructure/cser/cser_pipeline_service.py`). Pre-cropping would pre-empt its detector
and miss inline schemes / structures in tables.

- **PDF (Phase 0/1):** CSER's existing PyMuPDF re-render path is untouched.
- **Non-PDF (Phase 2):** CSER reads the **stored full-page PNG** we produced (via
  LibreOffice render) instead of re-rendering the source. This is the only CSER change,
  and it's additive.

This is also *why* full-page rendering is required for Word/HTML — not for chat alone, but
because a scientific Word doc can contain drawn structures we want CSER to find.

## 5. Operational status (consistency with existing decisions)

Per the prior architectural decision ("WorkflowStatus removed from aggregates — Temporal is
the source of truth"), we **do not** add a `parse_status` field to the `Artifact`
aggregate. Parse progress and failure are observable via the existing
`GET /artifacts/{id}/workflows` endpoint (proxies Temporal). The frontend shows "parsing…"
while the `parse-{artifact_id}` workflow runs and surfaces failures from its terminal
state. An artifact simply has no `Page`s until parsing completes.

## 6. Error handling

- **Unsupported MIME** → rejected at upload with a clear `4xx` (validation moves from
  "PDF only" to "supported set").
- **Parse failure** → Temporal retries `ParseArtifactWorkflow` per its retry policy; on
  exhaustion the workflow ends failed and is visible via the workflows endpoint.
- **Idempotent page creation** → page IDs are deterministic, `uuid5(artifact_id, str(index))`,
  so an activity retry re-creates the *same* pages rather than duplicating them. (Current
  `CreatePageUseCase` generates random IDs; the parse use case must supply deterministic IDs
  or guard on existence.)
- **Parse is atomic per artifact** → re-running the activity reproduces the same pages;
  no partial-state cleanup needed.

## 7. Testing

- **Segmenter unit tests** (the key runnable check): section segmentation from headings,
  large-section windowing, no-heading sliding-window fallback — on synthetic `ParsedDocument`
  fixtures. No framework beyond the existing test setup.
- **PDF parity test:** new async flow produces the same page count + per-page text +
  page images as the old saga for a known fixture PDF.
- **Idempotency test:** run `parse_artifact` twice → no duplicate pages.
- **Per-format parse tests:** golden-IR assertions for representative PPTX/DOCX (Phase 2),
  HTML/JATS (Phase 3) — assert key structure (N segments, a table detected, reading order).
- **Docling quality validation (Phase 0, gating):** run Docling on a real scientific-PDF
  corpus and compare extracted text/tables against PyMuPDF before retiring the old path.

## 8. Rollout — incremental, parity-gated

| Phase | Scope | Exit criteria |
|---|---|---|
| **0** | `DocumentParser` port + `ParsedDocument` IR + `DoclingParser` + `ParseArtifactUseCase` + `ParseArtifactWorkflow`. Route **PDF** through Docling in the new async flow, behind a flag, **alongside** the old saga. | Docling-on-PDF reaches parity (text, images, page count) on the validation corpus. |
| **1** | Thin the saga; flip upload to **async** (instant `201`, pages stream in); relax MIME validation; retire the synchronous PDF path. Frontend handles "parsing" state + streamed pages. | PDF ingestion fully on the new path; old path deleted. |
| **2** | PPTX + DOCX parsers/segmenters; LibreOffice full-page rendering; CSER reads stored page image for non-PDF. | PPTX + DOCX ingest end-to-end with images, CSER, NER, summaries. |
| **3** | HTML/JATS ingestion; structure-aware chunking on IR section boundaries. | Articles ingest; retrieval uses section-aware chunks. |
| **(B)** | *Deferred decision.* First-class tables/figures: structured payloads, retrieval, chat rendering, citation graph. | Triggered when retrieval/chat demonstrably needs it. |

PyMuPDF stays a dependency throughout (CSER uses it independently); only its role as the
*upload-time PDF parser* (`PDFService`) is retired.

## 9. Risks

1. **Docling quality on dense scientific PDFs** (multi-column, chemical schemes, complex
   tables) — biggest risk. Mitigated by the Phase 0 gating validation; old path stays until
   parity is proven.
2. **Docling speed** vs PyMuPDF — acceptable because parsing is now async in a workflow, but
   worth measuring (CPU vs GPU).
3. **LibreOffice dependency** weight in the worker image (Phase 2) — only added when Word/HTML
   actually land.
4. **Async upload contract change** — frontend must handle an artifact with no pages yet
   (Phase 1). Small, flagged.
