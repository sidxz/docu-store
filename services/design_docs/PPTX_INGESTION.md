# PPTX Ingestion (Multi-Format Phase 2, PPTX slice)

**Status:** Design / approved
**Date:** 2026-06-30
**Author:** Siddhant Rath (`sidx`)
**Parent design:** `MULTI_FORMAT_INGESTION.md` (this is the concrete PPTX slice of Phase 2)
**Scope:** Backend (`services/`) ingestion path only. Downstream extraction pipeline unchanged.

---

## 1. Why

We ingest PDFs via Docling today. PPTX is the next format. The `MimeType` enum
already lists `PPTX`, but ingestion is hard-gated to PDF at three points (upload
MIME validation, the parser registry, the Docling converter config), so a `.pptx`
upload is rejected at the front door.

## 2. Key finding that shapes the design

Docling parses PPTX **text + structure + per-slide provenance** correctly, but its
PPTX path (`SimplePipeline` + `MsPowerpointDocumentBackend`) **does not rasterize
slides** — `page.image` is `None` and page sizes come back in EMU (it reads the XML,
not a render). Verified empirically on a real 2-slide deck.

Page images are a hard requirement for parity:
- **CSER** runs a YOLO detector over the **full page image** to locate chemical
  structures (`cser_pipeline_service.py`); it re-renders the source with PyMuPDF
  (`fitz`), which cannot open `.pptx`.
- **Chat** uses stored page images as references; **doc-metadata** title extraction
  reads the source PDF via `fitz`.

There is no free pure-Python PPTX rasterizer. The realistic way to get slide images
is **LibreOffice** (`soffice --headless --convert-to pdf`). The user chose **full
parity** (images + CSER + chat), accepting the LibreOffice dependency. This is the
same mechanism DOCX will reuse.

Additionally: pages today are created from `parsed.pages` (the rendered-image list),
not from block provenance — `segment_document` iterates `parsed.pages`. With zero
rendered pages, PPTX would create **zero Pages**. Converting to PDF first sidesteps
this entirely: the rendered PDF yields real pages and images.

## 3. Decision

**Convert PPTX → PDF in the async parse workflow, then run the existing PDF pipeline
verbatim.** By the time any downstream step runs, the artifact has a real renderable
PDF. No parallel PPTX path; Docling parse, slide images, CSER, chat, segmentation,
and doc-metadata are all unchanged.

| Decision | Choice | Rationale |
|---|---|---|
| Strategy | Convert-to-PDF, reuse the PDF pipeline | Uniform; minimal diff; extends to DOCX free |
| Conversion engine | LibreOffice headless | Only free option that rasterizes Office formats |
| Where conversion runs | Async **parse workflow**, not upload | Upload must stay instant/durable — LibreOffice in the HTTP handler reintroduces the synchronous-upload problem the redesign removed |
| Original file | Kept as-is (`mime_type` stays `PPTX`, source stays `.pptx`) | Honest provenance + downloadable original |
| Rendered PDF | Derived blob at a deterministic key | Idempotent; activity retry re-converts/overwrites |
| `render_pdf_key` | **Free function** in application layer | Keeps the `artifacts/{id}/…` storage-key convention out of the domain aggregate |

### Rejected alternative
Docling-native PPTX for text + separately rendered images merged by slide index:
dual parse paths, two indexes to align, and it **still** needs LibreOffice for the
images. More code, marginal structure gain, no image benefit.

## 4. Components

| # | Change | Location |
|---|---|---|
| 1 | `OfficeToPdfConverter` port — `convert_to_pdf(source_storage_key, dest_storage_key) -> None` (reads source blob, writes derived PDF blob) | `application/ports/office_converter.py` (new) |
| 2 | LibreOffice impl — subprocess `soffice --headless --convert-to pdf`; injected `BlobStore` for I/O | `infrastructure/file_services/libreoffice_converter.py` (new) |
| 3 | `render_pdf_key(artifact) -> str` — `storage_location` if PDF, else `artifacts/{id}/derived/render.pdf` | `application/use_cases/storage_keys.py` (new; imports only `MimeType`) |
| 4 | Parse: if `mime != PDF`, `converter.convert_to_pdf(storage_location, render_key)` **before** `parser.parse(render_key)` | `application/use_cases/parse_artifact_use_case.py` |
| 5 | CSER + doc-metadata read `render_pdf_key(artifact)` instead of `artifact.storage_location` | `application/use_cases/compound_use_cases.py:92`, `application/use_cases/extract_document_metadata_use_case.py:141` |
| 6 | Relax MIME gate from PDF-only to a supported set `{PDF, PPTX}` | `application/use_cases/blob_use_cases.py:30` |
| 7 | DI: register converter; inject into `ParseArtifactUseCase`; add `PPTX → DoclingParser` to the parser registry | `infrastructure/di/container.py` |
| 8 | Add LibreOffice to the worker image | `Dockerfile` |

`embedding_use_cases.py:519` reads `storage_location` only to populate a DTO string —
left unchanged (it should reflect the true source location).

## 5. Data flow

```
upload .pptx
  └─ MIME gate accepts {PDF, PPTX}
  └─ Artifact.Created (mime=PPTX, storage=artifacts/{id}/source.pptx)
  └─ return 201 immediately (no parsing in request)

Artifact.Created → ParseArtifactWorkflow → ParseArtifactUseCase:
     render_key = artifacts/{id}/derived/render.pdf
     converter.convert_to_pdf(source.pptx, render_key)   # LibreOffice; durable + retryable
     parser.parse(render_key)                            # existing PDF Docling path → images included
     … persist page images / IR blob / segments / pages / text   (all unchanged)

Page.Created          → CSER reads render_key (fitz opens the PDF) ✓
Page.TextMentionUpdated → summaries / NER / doc-metadata (metadata reads render_key) ✓
```

The invariant from the parent design holds: `Page.Created` and
`Page.TextMentionUpdated` still fire from the parse use case; everything subscribed in
`pipeline_worker.py` works unmodified.

### Parser registry note
`PPTX → DoclingParser` in the registry means "DoclingParser handles PPTX." The
DoclingParser is PDF-configured; the parse use case guarantees `render_key` points at
a PDF (post-conversion) before calling it. Contract: **registry parsers receive a PDF
or natively-supported path; the use case converts Office formats to PDF first.**

## 6. Gotchas (baked into the design, not optional)

- **LibreOffice concurrency lock.** Parallel `soffice` invocations collide on the
  shared user profile and silently fail. Every call MUST get a unique
  `-env:UserInstallation=file://<tmpdir>`. Use a fresh temp dir per conversion.
- **Idempotency.** The derived key is deterministic; an activity retry re-converts and
  overwrites the same blob. No partial-state cleanup needed.
- **Conversion timeout.** `soffice` can hang; the subprocess call needs a timeout, and
  the parse activity already runs under Temporal retry/timeout policy.
- **Local dev.** This dev machine has no `soffice`. Real end-to-end PPTX needs
  `brew install --cask libreoffice` (`/Applications/LibreOffice.app/Contents/MacOS/soffice`).
  Unit tests stub the converter port; the live conversion gets one integration test
  gated on `soffice` presence.
- **Cleanup.** The derived PDF (`artifacts/{id}/derived/render.pdf`) is *not* specially
  deleted on artifact removal — and that's deliberate. The existing delete path only
  removes the source blob by exact key; page images (`pages/*.png`) and the IR blob
  (`parsed/document.json`) are already orphaned, and the blob store has no prefix-delete.
  The derived PDF joins that pre-existing orphan set. Proper fix = prefix cleanup of
  `artifacts/{id}/` — separate concern, out of scope for this slice.

## 7. Operational status

Consistent with the existing "WorkflowStatus removed from aggregates — Temporal is the
source of truth" decision: no `parse_status` field is added. Conversion failure ends
the `parse-{artifact_id}` workflow failed, visible via `GET /artifacts/{id}/workflows`.
An artifact simply has no Pages until parse (including conversion) completes.

## 8. Testing

- **`render_pdf_key`** — PDF returns `storage_location`; PPTX returns the derived key.
- **Parse-with-conversion** — stub `OfficeToPdfConverter` writes a fixture PDF to
  `dest_key`; assert pages + images created and `parser.parse` received `render_key`.
- **MIME gate** — PPTX accepted; an unsupported type still rejected with `4xx`.
- **Converter integration** — real `soffice` converts a fixture `.pptx`; skipped when
  `soffice` is absent (so CI without LibreOffice stays green until the image ships it).

## 9. Non-goals

- **Section-aware DOCX segmentation.** DOCX physical-page ingestion is **DONE** via the
  exact same convert-to-PDF mechanism (added `MimeType.DOCX` to the upload gate + parser
  registry, `libreoffice-writer` to the image; the converter needed zero changes). The
  caveat: Word has no inherent pages, so LibreOffice paginates by layout — a 2-section /
  ~90-paragraph doc renders to 4 arbitrary pages, each becoming a `Page`, so boundaries
  can split a section. The parent design's intended **section-based** segmentation (parse
  Docling-native DOCX heading structure to define `Page` boundaries) is **deferred** —
  add only if real-Word retrieval quality proves it's needed.
- Native PPTX structure / speaker notes (we parse the rendered PDF, not the XML).
- First-class structured table/figure objects (the parent design's deferred "(B)" tier).

## 10. Risks

1. **LibreOffice conversion fidelity** on dense scientific slides — generally high for
   slides (already page-shaped), but worth a spot check on a real deck.
2. **Worker image size** grows by LibreOffice (~hundreds of MB) — accepted per the
   scope choice.
3. **Conversion latency** — acceptable because parse is async; worth measuring.
