# Handoff: Compound-label reconciliation (source-side fix)

**Status:** problem statement + intended direction — NOT a plan. Start with
`superpowers:brainstorming`, then `superpowers:writing-plans`. The algorithm,
pipeline placement, and backfill strategy are deliberately left open for you to design.

**Date:** 2026-07-11
**Prereq shipped:** the lookup-side band-aid (#1) is already in the tree — see
"What #1 did" below. This handoff is the real fix (#3).

---

## The problem

Two extractors read the same document and disagree about the same compound's
label, and nothing reconciles them:

- **CSER** (structure extraction) read the label off the page image as
  **`CMX41O`** — capital letter **O**.
- **NER / the tag dictionary** (and the document text, folder names, bioactivity
  data) use **`CMX410`** — digit **zero**.

The compound structure store (`compound_embeddings` Qdrant collection) keys
structures by CSER's `extracted_id`. So a chat query "structure of CMX410"
(NER tags it `CMX410`) does an exact keyword lookup for `CMX410`, misses the
stored `CMX41O`, and reports "no structure found" — even though the structure is
right there. Bioactivity for the same query works, because that path matches on
the tag dictionary (which has `CMX410`).

This was originally mis-reported as a native-vs-manual tool-calling regression.
That was a red herring — native tool selection works fine (gemma4:31b picks
`search_compound_structure` correctly; the deterministic prefetch fires
regardless of mode). The failure is purely this label mismatch.

### Evidence (production, ned / workspace `6299d8cf-9db0-4d7f-b2cd-8893b8a02602`)

- `compound_embeddings` holds 3576 points. No `CMX410`; the only cmx-like ids are
  `CMX41O` and `mCMX41O` (letter O).
- `CMX41O` → `CS(=O)(=O)Nc1ncn(-c2cc(F)c(COc3ccc(OS(=O)(=O)F)cc3)c(F)c2)n1`
  (a real Pks13 covalent inhibitor — matches the "covalent adduct of cmx410 and
  the catalytic serine … in the acyltransferase domain of pks13" folder).
- Log signature of the miss: `compound_lookup_by_name_completed` with
  `raw_matches: 0` following a `chat.agentic_retrieval.structure_prefetch` of 0,
  while `chat.agentic_retrieval.bioactivity_prefetch` returns 24–29 data points.

This is almost certainly **not** a one-off. OCR glyph confusion (0/O, 1/I/l, 5/S,
8/B …) is systematic, and CSER extracts labels from images. Assume there is a
long tail of mislabeled compounds across the corpus; quantify it (see Open
questions → "measure the blast radius").

---

## What #1 did (the band-aid already in the tree)

`infrastructure/vector_stores/compound_qdrant_store.py`:
- `get_compounds_by_extracted_id` now tries the exact/formatting variants first
  (unchanged fast path), and **on miss** folds visually-confusable glyphs via
  `_confusable_variants()` and retries (miss-only, so a present id is never
  widened). New log event: `compound_lookup_glyph_fallback`.
- Safety property (tested in `tests/infrastructure/test_compound_name_matching.py`):
  it bridges only glyph-identical pairs (0↔O, 1↔I/l), **never** distinct digits —
  `CMX410` must never resolve to `CMX411` (a different analog-series compound).
- Verified against the live store: the variants resolve `CMX41O`.
- **NOT yet deployed to ned** — needs a services release + redeploy.

### Why #1 is not enough (why #3 exists)

- It only patches the *lookup*. The stored label is still wrong (`CMX41O`), so
  every other consumer of the raw `extracted_id` — search payloads, chat
  citations, the compounds UI, exports, any future feature — still shows/uses the
  wrong name.
- It covers only visual-glyph confusions. Other CSER extraction errors (dropped
  characters, transposed digits, wrong prefix like the `m`/`mCMX41O`) are not
  handled and arguably shouldn't be papered over at lookup time.
- It's a per-query cost that grows if more confusion classes are added.

The right fix is to make the store agree with itself: canonicalize the label at
the source so `extracted_id` matches what the document actually calls the compound.

---

## Intended direction (design it yourself)

Reconcile CSER's extracted compound label against the document's own known
compound names — the page/artifact **NER `compound_name` mentions** and/or the
**tag dictionary** — at or near extraction/embedding time, and canonicalize the
stored label to the document's name. Then downstream lookups need no glyph
gymnastics, and the raw label everyone reads is correct.

Same hard safety constraint as #1: reconcile only across glyph-equivalent / clear
OCR-noise differences. Never collapse two genuinely distinct analog-series
members. When in doubt, keep CSER's original and flag it — a wrong canonical
label is worse than an unreconciled one.

---

## Open questions for you to decide

1. **Where in the pipeline.** At CSER extraction output, at compound-embedding
   write time, or a projector? Candidate write path:
   - `infrastructure/vector_stores/compound_qdrant_store.py:213` — where
     `extracted_id` is written to the payload from `compound.get("extracted_id")`.
   - `application/use_cases/smiles_embedding_use_cases.py`,
     `application/use_cases/batch_reembed_use_cases.py`,
     `application/use_cases/compound_use_cases.py` — the embed/re-embed use cases.
   Whichever site has both the CSER label *and* the page's NER/tag context in hand.

2. **Matching algorithm.** Skeleton/confusable fold (reuse `_confusable_variants`
   / a shared skeleton fn)? Edit distance with guards? What confidence threshold,
   and what to do on no-candidate vs. multiple-candidate cases.

3. **Overwrite vs. augment.** Overwrite `extracted_id` with the canonical name, or
   keep the raw CSER label for provenance and add a separate
   `extracted_id_canonical` (indexed) that lookups prefer? The latter may make #1
   redundant *or* a clean complement — decide.

4. **Backfill — 3576 existing points.** This is the crux. Options to weigh:
   - Re-extract via `trigger_bulk_reprocess_compounds_use_case` /
     `BULK_REPROCESS_COMPOUNDS.md` — correct but expensive (CSER GPU) and subject
     to the deterministic-`page_id` purge-and-rebuild gotcha (see memory
     `project_docling_pipeline` — re-parse APPENDS a parallel page set unless you
     purge first).
   - In-place relabel: a migration that reconciles each stored `extracted_id`
     against that artifact's existing NER/tag data and rewrites the payload — no
     re-parse, no GPU, avoids the page_id gotcha entirely. Likely the cheaper,
     safer path. Idempotency + a dry-run/report mode are must-haves.
   - Decide whether backfill is even in scope now or a follow-up (the corpus
     migration for Docling enrichment was deliberately deferred — see memory).

5. **Measure the blast radius first.** Before designing, scan `compound_embeddings`
   `extracted_id`s per artifact against that artifact's tag_dictionary /
   NER mentions to count how many are mislabeled and by what confusion class. That
   number decides how much this is worth and which backfill option fits.

---

## Pointers

- Root-cause investigation + #1: this session's transcript; memory
  `project_compound_structure_lookup` (if written).
- Related: `design_docs/COMPOUND_EXTRACTION.md`, `design_docs/NER_PIPELINE.md`,
  `design_docs/BULK_REPROCESS_COMPOUNDS.md`,
  `project_chat_pipeline_architecture` (memory).
- Reproduce the miss: chat "structure of CMX410" in workspace `6299d8cf…`; watch
  `compound_lookup_by_name_completed raw_matches: 0` in `docu_store_api` logs on ned.
