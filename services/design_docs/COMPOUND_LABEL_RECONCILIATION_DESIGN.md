# Design: Compound-label reconciliation (source-side fix, #3)

**Status:** design — approved decisions locked, ready for `superpowers:writing-plans`.
**Date:** 2026-07-11
**Problem statement:** `design_docs/COMPOUND_LABEL_RECONCILIATION.md` (the handoff).
**Predecessor:** the lookup-side band-aid (#1) is in the tree (`compound_qdrant_store.py`, glyph fallback), not yet deployed to ned.

---

## 1. Problem (recap)

Two extractors read the same document and disagree on a compound's label:

- **CSER** reads the label off the page *image* → `CMX41O` (letter O).
- **NER** reads the compound name from the page *text* → `CMX410` (digit zero).

The compound structure store keys on CSER's `extracted_id`, so a chat lookup for
`CMX410` misses the stored `CMX41O` and reports "no structure found." OCR glyph
confusion (0/O, 1/I/l, 5/S, 8/B) is systematic, so this is a corpus-wide tail, not
a one-off.

The fix: reconcile CSER's label against the document's own NER compound names at
ingestion time and canonicalize the stored label. Downstream then needs no glyph
gymnastics and the label everyone reads is correct.

---

## 2. What the exploration established (the two load-bearing facts)

**Fact 1 — CSER and NER are concurrent Temporal branches with no join, and NER
usually finishes *last*.**

```
parse_artifact_use_case
  ├─ Page.Created ─────────► ExtractCompoundMentionsWorkflow (CSER, GPU, artifact_processing queue)
  │                            └─► Page.CompoundMentionsUpdated ─► EmbedCompoundSmilesWorkflow
  │                                                                  └─► writes extracted_id=CMX41O to Qdrant
  └─ Page.TextMentionUpdated ► NERExtractionWorkflow (slow LLM, temporal_llm_task_queue)
                                 └─► Page.TagMentionsUpdated ─► tag_mentions[compound_name]=CMX410   ← lands later
```

The two branches write **disjoint** aggregate fields and never synchronize.
Consequence: reconciling *inside* `EmbedCompoundSmilesUseCase` at first write is a
dead end — the NER name is usually not on the page yet. Reconciliation must be
**driven by NER completing**, not by the compound-embed step.

**Fact 2 — `extracted_id` is stored in TWO derived places.**

- Qdrant `compound_embeddings` payload — `compound_qdrant_store.py:213` (the chat lookup / the bug).
- Mongo `page_read_models.compound_mentions[].extracted_id` — `page_projector.py:36` (the compounds UI / API).

Both are *projections of the `CompoundMention` aggregate*. A Qdrant-only patch
leaves the Mongo copy wrong (UI still shows `CMX41O`) and is reverted by any future
re-embed. This is why the fix goes at the source.

---

## 3. Locked decisions

| Decision | Choice | Rationale |
|---|---|---|
| **Scope / sequencing** | Measure first, then live fix. Backfill write decided by the blast-radius number. | Measurement is nearly free (dry-run of the backfill script). Avoids committing GPU/compute before knowing the tail size. |
| **Fix location** | At the source: rewrite `extracted_id` on the aggregate, emit a corrected event, let the existing cascade re-derive **both** Qdrant and Mongo. | Two derived stores; correcting the source fixes both and is durable against re-embeds. Provenance (the raw CSER label) is preserved for free in the event log. |
| **Trigger** | Rendezvous — fire reconciliation from **both** `TagMentionsUpdated` and `CompoundMentionsUpdated`; idempotent; only emit on change. | Common case: NER last → `TagMentionsUpdated` does the work. Reverse race and bulk-reprocess re-extract → `CompoundMentionsUpdated` self-heals. |
| **Matching** | Glyph-skeleton equality only (reuse #1's groups `0Oo/1IlL/5S/8B`). Never bridge distinct digits. Precision over recall. | Same hard safety constraint as #1: `CMX410` must never resolve to `CMX411`. |
| **Backfill mechanism** | Re-run the reconcile use case per page in-process (the `reembed_docling_enrichment.py` pattern), not a bespoke Qdrant patch. | Reuses the live path; emits corrected events so both stores self-correct. No GPU/CSER — CSER re-extraction is *rejected* (deterministic OCR reproduces the same wrong label). |
| **#1 (lookup fallback)** | Keep as the safety net for the un-reconciled tail. | Covers reverse-race stragglers, pages with no NER name, and ambiguous cases — at query time, where source reconciliation can't reach. |

---

## 4. Architecture

### 4.1 The matcher (pure domain service)

`domain/services/compound_label_matcher.py` — no I/O, fully unit-testable.

```python
_CONFUSABLE_GROUPS = ("0Oo", "1IlL", "5S", "8B")   # same groups as #1

def glyph_skeleton(label: str) -> str:
    """Uppercase, strip hyphens/spaces, fold each confusable glyph to its group's
    canonical digit (O→0, I/l→1, S→5, B→8). Two labels are glyph-equal iff equal skeletons."""

def reconcile_label(cser_label: str, candidate_names: Iterable[str]) -> str | None:
    """Return the document name to canonicalize to, or None to keep the CSER label.
    Match = same glyph-skeleton. Skeleton never merges distinct digits, so at most
    one distinct compound can match; surface-form variants (casing/hyphenation of the
    same skeleton) collapse to one — pick the most frequent / cleanest. Zero matches → None."""
```

Ambiguity note: because the skeleton preserves distinct digits, a CSER label can
match **at most one** real compound among the document's names. "Multiple candidates"
only arises as casing/format variants of the *same* name, which collapse to one.
The only keep-original case is **zero** matches.

> Layering: #1's identical group constant lives in `infrastructure/vector_stores/compound_qdrant_store.py`.
> Leave #1 as-is for now (it's shipped-pending-deploy). Optional low-priority follow-up:
> refactor #1 to import the domain matcher so the groups have a single home.

### 4.2 Live path — `ReconcileCompoundLabelsUseCase`

`application/use_cases/reconcile_compound_labels_use_case.py`

1. Load the Page aggregate.
2. `names = {tm.tag for tm in page.tag_mentions if tm.entity_type == "compound_name"}`.
   (Same-**page** scope — zero extra reads; the cross-page tail is swept by the backfill.)
3. Early-return (no-op) if `not page.compound_mentions` or `not names`.
4. For each `CompoundMention`, `target = reconcile_label(m.extracted_id, names)`;
   if `target and target != m.extracted_id`, replace via `m.model_copy(update={"extracted_id": target})`
   (all other fields preserved — `smiles`, `canonical_smiles`, `confidence`, …).
5. If nothing changed → return without emitting (idempotent).
6. Else `page.update_compound_mentions(reconciled_list)` — **reuses the existing
   method/event**, so `PageProjector` (→ Mongo) and `EmbedCompoundSmilesWorkflow`
   (→ Qdrant) re-derive with no new write code. Log `compound_labels_reconciled`
   with before/after for observability.
7. `page_repository.save(page)`. On `ConcurrencyError`, raise → the Temporal activity retries.

### 4.3 Temporal placement — "at what time"

Mirror the existing `Trigger → Workflow → Activity → UseCase` pattern (template:
`smiles_embedding_workflow.py`):

- `infrastructure/temporal/workflows/reconcile_compound_labels_workflow.py` —
  `@workflow.defn(name="ReconcileCompoundLabelsWorkflow")`, activity
  `"reconcile_compound_labels"`, `start_to_close_timeout≈2min`, RetryPolicy 3 attempts
  (retries matter — the aggregate save can raise `ConcurrencyError`).
- Activity registered in `worker.py`, factory-injected `ReconcileCompoundLabelsUseCase`
  (mirror the `embed_compound_smiles` activity).
- `orchestrator.py`: `start_reconcile_compound_labels_workflow(page_id)`,
  `task_queue="artifact_processing"`, id `reconcile-compound-labels-{page_id}`, reuse
  policy matching the SMILES workflow's (re-fireable).
- `application/workflow_use_cases/trigger_compound_label_reconciliation_use_case.py` —
  thin trigger, mirrors `TriggerSmilesEmbeddingUseCase`.

**Wiring** in `pipeline_worker.py`:
- `Page.TagMentionsUpdated` handler (`:306`) → add the reconcile trigger (common case).
- `Page.CompoundMentionsUpdated` handler (`:289`) → add the reconcile trigger (reverse
  race + bulk-reprocess self-heal).

**When it runs:** at the rendezvous of the two branches — practically ~a few minutes
after NER completes for a page. Whichever branch finishes last does the real work;
the earlier trigger is a no-op (step 3).

### 4.4 No cascade loop

Reconcile emits `CompoundMentionsUpdated`, which re-triggers (a) SMILES re-embed —
intended, writes the canonical label to Qdrant; (b) reconcile again — re-runs, finds
labels already canonical, emits nothing, terminates. One extra no-op reconcile per
correction. `SmilesEmbeddingGenerated` is terminal (not subscribed), so nothing loops
back into NER or CSER.

### 4.5 Event flow (normal case: NER last)

```
1. CompoundMentionsUpdated (CSER, CMX41O)
     ├─► reconcile: names={} (NER not done) → no-op
     └─► EmbedCompoundSmiles → Qdrant extracted_id=CMX41O          (temporarily wrong)
2. TagMentionsUpdated (NER, compound_name=CMX410)
     └─► reconcile: CMX41O ~ CMX410 → change → update_compound_mentions → CompoundMentionsUpdated(CMX410)
3. CompoundMentionsUpdated (reconciled, CMX410)
     ├─► reconcile: already canonical → no emit (stop)
     ├─► PageProjector → Mongo page_read_models extracted_id=CMX410   ✔
     └─► EmbedCompoundSmiles → Qdrant extracted_id=CMX410              ✔
```

Reverse race (NER first) converges the same way via the `CompoundMentionsUpdated`
trigger. Eventually consistent per page.

---

## 5. Measurement + backfill script

`scripts/reconcile_compound_labels.py` — in-process, DI via `create_container()`
(pattern: `reembed_docling_enrichment.py`). Flags: `--workspace`, `--artifact`,
`--dry-run` (default true), `--apply`.

- **Per-artifact scope** (wider recall than the live path): read Mongo
  `page_read_models` for the artifact — each doc co-locates the wrong label
  (`compound_mentions[].extracted_id`) and the candidate names
  (`tag_mentions[compound_name]`). Union names across the artifact's pages.
- **Dry-run (measurement):** report, per confusion class, how many labels would
  change — `{artifact_id, page, before, after, class}`. This is the blast-radius
  number that decides whether to `--apply`. **No writes.**
- **Apply:** run `ReconcileCompoundLabelsUseCase` per page → corrected events →
  both stores self-correct. Idempotent (re-run = no-op once canonical). No GPU.

Sequencing per the locked decision: **build + dry-run first, report, then decide
`--apply`.**

---

## 6. Edge cases & safety

- **Distinct analog-series members** (`CMX410` vs `CMX411`): different skeletons →
  never merged. Locked by matcher tests (mirror `test_compound_name_matching.py`).
- **No NER name for a compound** (structure with no text label): zero matches →
  keep CSER label. #1 covers it at lookup.
- **Ambiguous only as casing/format**: collapse to one surface form (most frequent /
  cleanest). Genuine cross-compound ambiguity cannot occur under skeleton matching.
- **Concurrency**: aggregate save races with a concurrent CSER/NER write →
  `ConcurrencyError` → activity retry reloads and re-reconciles. Existing machinery.
- **Bulk reprocess** re-extracts raw labels → `CompoundMentionsUpdated` → reconcile
  self-heals.
- **Non-glyph CSER errors** (dropped/transposed chars, wrong prefix like `mCMX41O`):
  **out of scope** — precision over recall; #1 doesn't handle them either.

---

## 7. Components

**New**
- `domain/services/compound_label_matcher.py`
- `application/use_cases/reconcile_compound_labels_use_case.py`
- `application/workflow_use_cases/trigger_compound_label_reconciliation_use_case.py`
- `infrastructure/temporal/workflows/reconcile_compound_labels_workflow.py`
- `reconcile_compound_labels` activity (in the activities module / `worker.py`)
- `scripts/reconcile_compound_labels.py`
- `tests/domain/test_compound_label_matcher.py`
- `tests/application/test_reconcile_compound_labels_use_case.py`

**Modified**
- `infrastructure/pipeline_worker.py` — 2 trigger wires (`:289`, `:306`)
- `infrastructure/temporal/orchestrator.py` — `start_reconcile_compound_labels_workflow`
- `infrastructure/temporal/worker.py` — register workflow + activity
- `infrastructure/di/container.py` — wire use cases
- `design_docs/NER_PIPELINE.md` — fix stale entity name (`compound` → `compound_name`)

---

## 8. Testing

- **Matcher (pure):** `glyph_skeleton` folds each group; `reconcile_label` returns
  `CMX410` for `CMX41O` vs `{CMX410}`; returns `None` for `{CMX411}` (distinct digit)
  and for `{}`; collapses `{CMX410, cmx410}` to one. Mirror #1's safety assertions.
- **Use case:** page[compound `CMX41O` + tag compound_name `CMX410`] → emits
  `CompoundMentionsUpdated` with `extracted_id=CMX410`, other fields intact; re-run →
  no emit; no compound tags → no emit; `ConcurrencyError` propagates.
- **Script:** dry-run counts without writing (light test on the counting/reporting).

---

## 9. Out of scope

- Executing the corpus write-backfill — gated on the measurement (build + dry-run now).
- Non-glyph OCR errors and cross-document (workspace-wide) name matching.
- Chat table rendering / other deferred Phase D work.
- Deploying #1 (separate services release, already tracked).
