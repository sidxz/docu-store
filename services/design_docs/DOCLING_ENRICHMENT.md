# Docling Structure Enrichment — Ingestion, Search & Chat

**Status:** Design / proposed
**Date:** 2026-06-29
**Author:** Siddhant Rath (`sidx`)
**Scope:** Use the document structure Docling already produces (captions, heading hierarchy, table cells, figure crops) to enrich the ingestion, search, and chat pipelines. Builds on the Docling ingestion path (see `MULTI_FORMAT_INGESTION.md`). Backend only.

---

## 1. Why

Our Docling parser produces a rich `DoclingDocument`, but we map it down to a flat list of typed `Block`s and then **linearize to markdown text + full-page images** — discarding captions, heading levels, table cell structure, and figure crops. Two observations reframe the opportunity:

1. **The IR blob is a stranded asset.** `ParseArtifactUseCase` writes the full structure to `artifacts/{id}/parsed/document.json` on every parse and **nothing reads it** (`parse_artifact_use_case.py`). The structure is already persisted; we just don't consume it.
2. **Chat is pre-wired for structure.** `ContentBlockDTO(type="table"/"molecule")` and the `structured_block` SSE event exist but are **never populated** (`chat_dtos.py`), and deep-thinking already does multimodal synthesis (page images → `images_b64` in `adaptive_synthesis.py`). The seams for tables/figures-in-answers already exist.

And the sharpest insight on the data:

> **Captions are the cheapest, highest-value signal we throw away.** A figure/table caption ("Figure 3: aminopyrimidine SAR — IC50 vs hERG") is a dense, human-written description of exactly the content Docling otherwise drops as `[Figure]`. `_to_block` never sets `Block.caption`. Pulling captions into the text pipeline recovers much of the "figures are invisible to retrieval" gap **for almost nothing** — and, critically, feeds `structflo-ner` (see §3).

**What we drop today, and what each pipeline could consume:**

| Docling gives | Now | Ingestion | Search | Chat |
|---|---|---|---|---|
| Captions (fig+table) | dropped | → linearized text | → searchable + payload | → label/show figures+tables |
| Heading levels / section path | dropped (all `#`) | → real hierarchy | → `section_path` filter + rerank signal | → "in Methods…" context + grounding |
| Table cell structure | in IR, unused downstream | keep intact | don't split across chunks; table filter | render real tables (`ContentBlockDTO`) |
| Figure crops | dropped (`[Figure]`) | store as blobs | figure retrieval | multimodal context + cite/show figures |
| Bounding boxes | dropped | — | — | (UI highlight — out of scope) |

**Validated gap:** on real chemistry decks (aminopyrimidines, GyrB) Docling buckets dense **assay data panels** as figures and drops their text; today those values reach chat only via the coarse page-image→summary path, and are invisible to `structflo-ner`.

## 2. Goals / Non-goals

**Goals**
- Capture the structure Docling already computes and flow it into ingestion, search, and chat.
- Boost `structflo-ner` yield (compounds/bioactivity/targets) by feeding it captions and, later, figure-derived text.
- Make figures and tables first-class: retrievable, citable, and renderable in chat.
- Reuse dormant capability (the IR blob; chat's structured-block + multimodal seams) rather than building parallel subsystems.

**Non-goals (explicit YAGNI)**
- No CLIP/image-embedding model for figures in v1 — caption-text embedding ≈ 80% of figure retrieval value for ~10% of the effort. Add only if "find visually similar figures" becomes a real need.
- No bounding-box / spatial UI features (pixel-region highlighting) yet.
- No separate `table_embeddings` / `figure_embeddings` Qdrant collections until query patterns prove they're needed — start by tagging points in `page_embeddings`.
- No flurry of new aggregate events for derived parse artifacts (see §4).
- **Do not reimplement chemical-structure detection** — `structflo-cser` owns it (see §3).

## 3. How this fits the existing extractors (`structflo-cser` / `structflo-ner`) — first-class constraint

These two libraries are the heart of extraction and the enrichment must wrap **around** them, feeding them rather than competing.

**`structflo-cser` = vision → molecules.** `CserPipelineService.extract_compounds_from_pdf_page(storage_key, page_index)` renders the **source PDF** page via `fitz` @2× (`cser_pipeline_service.py:61-67`) — independent of Docling — and runs `ChemPipeline.process(image)` (detect drawn structures anywhere on the page → `(SMILES, label, confidence)`) → `CompoundMention` → ChemBERTa → `compound_embeddings`. Trigger: `Page.Created`.

**`structflo-ner` = text → entities/bioactivity.** `StructfloNERExtractor.extract(page.text_mention.text)` runs a fast gazetteer (`accession_number, gene_name, screening_method, target`) ∥ the LLM **TB profile** (bioactivity values, mechanisms, diseases, compound names, targets, 30+ types) and merges (`structflo_ner_extractor.py`). → `TagMention` → tags/`entity_types` → tag aggregation + `tag_dictionary` + Qdrant payloads + chat's `search_structured_bioactivity` tool. Trigger: `Page.TextMentionUpdated`.

So **CSER reads the page as pixels (molecules); NER reads it as text (everything else).** Implications that bind the design:

1. **NER is a consumer of text quality.** Phase A's captions/headings flow into `page.text_mention.text`, so NER immediately mines bioactivity/compounds/targets from captions it is blind to today — a free yield boost that compounds through tags, search payloads, and chat's bioactivity retrieval. (NER runs on the **whole page** text, not chunks → structure-aware chunking in Phase B does not affect it; Docling-captured tables already linearize into the page text, so NER already mines table bioactivity.)

2. **CSER is already the figure pipeline for chemical structures → divide labor, don't duplicate.**
   - Chemical-structure drawings → **CSER** (unchanged; **never feed it Docling figure-crops** — it needs the full page because structures appear inline and in tables).
   - Plots / charts / schemes / gels / micrographs / **data panels** → the **new figure pipeline** (Phase C).
   - Optional cross-link: a Docling figure region overlapping a CSER hit ⇒ mark the figure as a chemical structure (link crop ↔ `CompoundMention`). Nice-to-have.

3. **Deep integration — figure → text → NER.** Assay **data panels** Docling drops are invisible to both NER (not text) and CSER (not a molecule). The figure pipeline can produce **text from figures** — caption (cheap) and optionally a VLM description/OCR of the crop — and route it back through `structflo-ner`, letting NER mine bioactivity/compounds from figures it currently can't read. Highest value, heavier (VLM) → Phase C+ option.

## 4. Storage model (the key decision)

Structure derived at parse time is **not domain state** — consistent with the project's "WorkflowStatus removed from aggregates; don't put derived/operational data on aggregates" precedent. Therefore:

- **IR blob = source of truth for all structure.** Enrich the parser to capture captions/levels/section-paths/figure-refs (the fields largely exist on `Block`); the blob is already written per parse. **Phase B is where we start reading it.**
- **Figure crops = new blobs** at `artifacts/{id}/figures/{page_index}_{block_index}.png` (binary; can't live in JSON).
- **Search signals = Qdrant chunk payload** (block_type, section_path, is_table, is_figure, caption), written at embed time — no Mongo/event needed.
- **Chat/UI structure = read the IR blob (and figure blobs) on demand** — chat already has `artifact_id`/`page_id`; the per-artifact IR JSON is small. Avoids new events and read-model churn.
- **Aggregate events added: target zero.** The enriched text still flows via the existing `Page.TextMentionUpdated`. If on-demand IR reads later prove hot, project figure/table refs to the read model behind one event — deferred, not now.

**Migration:** enrichment benefits **new** ingestions immediately. Existing artifacts need a **re-parse** (to enrich the IR + emit figure crops + re-write `text_mention`) and a **re-embed** (Phases A/B change chunk text). The async parse workflow is idempotent (deterministic page ids) and re-runnable; batch re-embed already exists. Treat backfill as an ops step per phase.

## 5. The enrichment ladder

### Phase A — Capture & linearize (parser-only, near-zero downstream change)

**What:** In `docling_parser._to_block`, populate `Block.level` (heading depth) and `Block.caption` (`item.caption_text(dl_doc)` for picture/table items); compute `Block.section_path` by maintaining a heading stack while iterating items in reading order. `linearize_blocks` then emits real heading hierarchy, `[Figure: {caption}]`, and table captions.

**Files:** `infrastructure/file_services/docling_parser.py` (`_to_block`, new heading-stack pass), `application/dtos/parsed_document.py` (`Block.section_path: list[str]`; `linearize_blocks`).

**Effect:** `page.text_mention.text` gains captions + structure → better chunks/embeddings/summaries **and a direct `structflo-ner` yield boost** (§3.1). No new storage, events, or API.

**Interacts:** NER (consumer — primary win). CSER (none).

**Tests:** parser populates level/caption/section_path; linearize reflects them; a caption with assay text round-trips into the linearized page text.

### Phase B — Structure-aware retrieval (ingestion + search)

**What:** Replace blind 1000-char chunking with **block-aware chunking** that (a) never splits a table across chunks (a table is one chunk; if oversized, split by rows repeating the header), (b) keeps a heading with its following content, (c) caps size but aligns to block boundaries. Carry per-chunk metadata into the `page_embeddings` payload: `block_type`, `section_path`, `is_table`, `is_figure`, `caption`. Add Qdrant keyword indexes for `is_table`, `is_figure`, `block_type`. Add search filters (`block_types`, `section`, `is_table`/`is_figure`) and feed `section_path` + `caption` into the reranker document.

**Key seam — start reading the IR blob:** `GeneratePageEmbeddingUseCase` (and `BatchReEmbed…`) read `artifacts/{artifact_id}/parsed/document.json`, select blocks where `source_page_index == page.index`, and chunk block-aware. If the IR blob is absent (pre-Phase-A artifacts), fall back to the current char chunker on `text_mention.text`.

**Files:** new `infrastructure/text_chunkers/block_aware_chunker.py`; `application/use_cases/embedding_use_cases.py` (read IR, block-aware path, payload fields); `application/use_cases/batch_reembed_use_cases.py` (same); `infrastructure/vector_stores/qdrant_store.py` (payload + indexes + filter builder); `application/dtos/embedding_dtos.py` + `interfaces/api/routes/search_routes.py` (new filters); `infrastructure/rerankers/cross_encoder_reranker.py` (document text includes section/caption).

**Interacts:** NER unaffected (whole-page). CSER unaffected. Requires re-embed of existing corpus to benefit.

**Tests:** chunker keeps a table intact; chunker keeps heading with its section; payload carries block_type/section/is_table/is_figure; a `is_table` filter returns only table chunks; reranker sees section/caption.

### Phase C — First-class figures (non-molecule) (ingestion + search + chat)

**What:**
- **Capture crops:** enable `generate_picture_images=True`; `ParseArtifactUseCase` stores each non-trivial figure crop via `item.get_image(dl_doc)` → `artifacts/{id}/figures/{page}_{idx}.png`; figure refs (caption, blob key, page_index, optional bbox) recorded in the IR blob.
- **Retrieve figures:** figure captions are already retrievable text after Phase A; Phase C makes the figure a **first-class result/source** — when a chunk is a figure (or a figure caption matches), the result carries `is_figure`, `caption`, and the crop blob key. (Optional, gated: a VLM pass that describes each crop → richer retrievable text, and/or routes that text through `structflo-ner` per §3.3.)
- **Chat multimodal:** in thinking/deep-thinking, load relevant **figure crops** (not just full pages) into the existing `images_b64` path (`adaptive_synthesis.py`) with their captions as text hints; surface figures as sources; serve crops via a new `GET /artifacts/{id}/figures/{n}` endpoint (mirrors the page-image endpoint).
- **CSER division (explicit):** figures here are **non-molecule**; CSER continues to own chemical structures from the full page. Optional cross-link figure↔compound by page/bbox overlap.

**Files:** `docling_parser.py` (crop capture), `parse_artifact_use_case.py` (store figure blobs + refs), `interfaces/api/routes/artifact_routes.py` (figure endpoint), chat retrieval/context-assembly + `adaptive_synthesis.py` (figure crops into `images_b64`), `thinking_agent.py` (load figure crops). Optional: a figure-VLM activity + a `figure→NER` hop.

**Interacts:** CSER (division of labor — first-class constraint). NER (optional figure→text→NER deep hop).

**Tests:** crops stored at expected keys; figure endpoint serves a crop; a figure result carries caption + crop key; deep-thinking includes a figure crop in `images_b64`.

### Phase D — Structured tables + block-level chat (search + chat)

**What:** Read table structures (rows) from the IR; surface them as retrievable units and **render real tables in answers** by populating the existing `ContentBlockDTO(type="table", headers, rows)` + emitting `structured_block` SSE events. Add **block-level citations** — `SourceCitationDTO.block_id` + `section_path`, carried on `RetrievalResult` and assigned in `context_assembly` — so chat cites "Table 3 in Results" rather than "page 5". Feed `section_path` breadcrumbs into the synthesis prompt and grounding check.

**Files:** `infrastructure/chat/models.py` (`RetrievalResult.block_type/table_rows/block_id/section_path`), `infrastructure/chat/nodes/context_assembly.py` (carry + assign), `infrastructure/chat/nodes/adaptive_synthesis.py` (render tables / pass breadcrumbs), `application/dtos/chat_dtos.py` (`SourceCitationDTO.block_id/section_path`; populate `ContentBlockDTO`), `infrastructure/chat/agent.py`/`thinking_agent.py` (emit `structured_block`, include in done event), `infrastructure/chat/nodes/inline_verification.py` (block-aware grounding).

**Interacts:** NER already mines tables (no change). Chat scaffolding already exists (populate it).

**Tests:** a table result populates `ContentBlockDTO`; a `structured_block` event is emitted; a citation carries `block_id`/`section_path`; synthesis prompt includes section breadcrumbs.

## 6. Sequencing & first plan

Recommended order, each its own implementation plan: **A → B → C → D.** A is a cheap, broad, low-risk foundation (and a free NER boost); B makes retrieval structure-aware; C closes the validated figure gap; D delivers the chat UX. **First implementation plan: Phase A + B** (foundation), unless we choose to push straight through C.

## 7. Risks / open questions

1. **Re-parse + re-embed cost** for the existing corpus (each phase). Backfill is an ops step; bound by Temporal concurrency.
2. **Docling caption/level/crop API specifics** (`caption_text`, heading level, `get_image`) are version-dependent — verify against installed `docling` (2.107.0) at implementation, as in the ingestion build.
3. **Figure crop volume/storage** — many crops per deck; cap by min-size/relevance; JPEG for storage.
4. **VLM cost** (Phase C+ figure→text) — gate behind config; not in the base figure phase.
5. **Read-IR-on-demand hotness** — if chat reads the IR blob per query and it becomes hot, project figure/table refs to the read model behind one event (deferred).
6. **Section-path normalization** for filtering (case/whitespace) — mirror the existing `tag_normalized` pattern.

## 8. Testing strategy

Per-phase unit tests as listed above. Plus a **retrieval-quality check on real decks** (reuse the Docling-gate harness approach): measure whether captions/structure improve recall of bioactivity values and figure-described findings vs the current flat-text baseline, before committing each phase's backfill.
