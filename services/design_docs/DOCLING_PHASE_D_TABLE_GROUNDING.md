# Docling Enrichment Phase D — Per-Table Entity Grounding (ingestion tagging)

**Status:** Design / approved (brainstorm 2026-06-29)
**Date:** 2026-06-29
**Author:** Siddhant Rath (`sidx`)
**Scope:** Backend, ingestion-only. Part of the Docling structure-enrichment series (`DOCLING_ENRICHMENT.md`). Builds on Phase A (IR capture) + Phase B (block-aware chunking, per-chunk Qdrant payload).

---

## 1. Problem

Chat sometimes answers a target-specific question with values from the **wrong target** — e.g. a query for **Rho** IC50 values surfaces a **PptT** table's values. Root cause, confirmed on both sides:

- **Ingestion (the bug):** every chunk of a page inherits the page's *union* of NER tags. `_build_page_metadata` (`application/use_cases/batch_reembed_use_cases.py:95-104`, mirrored in `embedding_use_cases.py:253-257`) sets `tags`/`tag_normalized`/`entity_types` from `page.tag_mentions` — every entity NER found *anywhere* on the page — and applies them as shared metadata to *every* chunk. A page with a Rho table and a PptT table tags the PptT table chunk `[rho, pptt]`.
- **Retrieval (context only; unchanged here):** `infrastructure/chat/nodes/query_planning.py` correctly extracts the query's target and filters on `tag_normalized`. The PptT table chunk passes a `rho` filter because of the page-union tag, and vector similarity ranks it high (it is an IC50 table) → wrong values surface.

The table "floats free" of what it is actually about.

## 2. Goals / Non-goals

**Goals**
- Tag each **table** chunk with the entities *it* is about (scoped to the table), not the page-wide union.
- Keep each table grounded: its own entities + the document subject + provenance (section, caption, authors, title, date) as **distinct** fields.
- Fix the *data* at ingestion so the *existing* retrieval naturally stops matching the wrong table.

**Non-goals (explicit)**
- **No retrieval/query changes.** `query_planning.py`, search use cases, filters, rerank — untouched. (User constraint.)
- **No new models / LLM / extra NER passes.** Reuse the page-level NER output already produced.
- **No chat table rendering** (`ContentBlockDTO`/`structured_block`/block-level citations) — that half of Phase D is deferred.
- **No new aggregate events / read-model fields.** Lives in the Qdrant chunk payload, like Phase B.
- **Figures out of scope** (caption-only; trivial later extension via the same helper).

## 3. Design

### 3.1 Attribution helper (pure)

New pure function, co-located with the block-aware chunker (`infrastructure/text_chunkers/block_aware_chunker.py`):

```python
def scope_table_entities(
    candidates: list[tuple[str, str | None]],  # (tag, entity_type) from page NER
    local_text: str,                            # table markdown + caption + section_path
) -> dict:
    """Keep entities whose surface form appears in the table's local text on a
    word boundary (case-insensitive). Returns {tags, tag_normalized, entity_types}
    for the table chunk payload; empty lists when nothing matches."""
```

- Match = `re.search(r"\b" + re.escape(tag.lower()) + r"\b", local_text_lower)`. **Word-boundary, not substring** → candidate `rho` does not match `rhodamine`.
- Returns deduped `tags` (original casing), `tag_normalized` (lowercased), `entity_types` (types of the kept entities).
- Takes plain `(tag, entity_type)` tuples (not `TagMention`) so it stays decoupled and trivially unit-testable. Pure: no models, no IO.

### 3.2 Payload change — table chunks only

In both embed paths (`GeneratePageEmbeddingUseCase`, `BatchReEmbedArtifactPagesUseCase`), after the block-aware chunks + `chunk_metadata` list are built, for each chunk where `is_table`:

- `local_text = chunk.text + " " + " ".join(chunk.section_path)` — the table markdown already includes the caption (Phase B `_table_group_chunk`); `section_path` is added explicitly.
- `candidates = [(tm.tag, tm.entity_type) for tm in page.tag_mentions]`.
- Merge `scope_table_entities(candidates, local_text)` into that chunk's `chunk_metadata[i]`.

Phase B's upsert applies the shared page-union `metadata` first, then `chunk_metadata[i]` on top (`infrastructure/vector_stores/qdrant_store.py::upsert_page_chunk_embeddings`), so the scoped `tag_normalized`/`entity_types`/`tags` **override** the union for table chunks. Non-table chunks carry no tag keys in `chunk_metadata` → keep today's page-union behavior (no recall regression where scoping isn't needed).

> Note: this makes `tag_normalized` mean "table-scoped entities" on table chunks but "page-union" on prose chunks. Intentional and surgical — the pollution is a table phenomenon (dense values, weak in-vector target signal); prose usually names its own target in-text.

### 3.3 Grounding already present (no new work)

A table chunk ends up carrying, in **distinct** fields:
- **Its own entities** — scoped `tag_normalized`/`entity_types` (§3.2).
- **Document subject** ("deck is about Rho") — `artifact_tag_normalized` (aggregated targets/authors/year), already synced to chunk payloads via `SyncArtifactMetadataToVectorStoreUseCase` / `scripts/backfill_artifact_qdrant_metadata.py`.
- **Provenance** — `section_path` / `caption` / `is_table` from Phase B; `artifact_title` / `authors` / `presentation_date` already resolved at retrieval time from the read model (`infrastructure/chat/tools/retrieval_tools.py`).

So nothing floats: own-entities + doc-subject + provenance, none of them conflated.

### 3.4 Key decision — precision over recall

If no candidate attributes locally, the table chunk gets **empty** table-level entity tags (not the page union). It still carries the document subject + section/caption (which usually name the target). Rationale: a *wrong* target tag pollutes chat (the reported failure); a *missing* one degrades gracefully to doc-level + vector match. In practice the target is almost always in the table's caption or section heading — both in `local_text` — so genuine misses are rare.

## 4. Touchpoints

- `infrastructure/text_chunkers/block_aware_chunker.py` — add `scope_table_entities`.
- `application/use_cases/embedding_use_cases.py` — `GeneratePageEmbeddingUseCase`: scope table-chunk metadata.
- `application/use_cases/batch_reembed_use_cases.py` — `BatchReEmbedArtifactPagesUseCase`: same.
- Tests: `tests/infrastructure/test_block_aware_chunker.py` (helper) + assertions in the two embed-use-case tests.

No changes to ports, search DTOs, the Qdrant schema (`tag_normalized`/`entity_types` keys already exist + are indexed), retrieval, or DI.

## 5. Testing

Pure unit tests on `scope_table_entities`:
- PptT in caption/cells, Rho only elsewhere on the page → keeps `pptt`, drops `rho`.
- Word-boundary: candidate `rho` does **not** match `rhodamine`.
- Section heading contributes: table under `section_path=["Rho inhibitors"]`, cells don't repeat the name → `rho` kept.
- No local match → empty lists.

Embed-path test (one per use case): a table chunk's upserted `tag_normalized` equals the scoped set (not the page union); a prose chunk on the same page keeps the union.

## 6. Backfill

Benefits **new** ingestions immediately. Existing docs gain it only via the already-deferred re-parse + re-embed (needs the IR blob + the page-id migration tracked separately). No additional backfill mechanism is introduced here.

## 7. Out of scope / future

- Chat table **rendering** + block-level citations (original Phase D second half).
- Figure-chunk scoping (same helper, gated on `is_figure`).
- "Primary document subject" (dominant target across pages) as a cleaner doc-subject than the aggregated union — refinement only if needed.
- Scoped re-NER / LLM table descriptor (richer binding) — only if locality attribution proves too lossy in the §8 retrieval-quality check.
