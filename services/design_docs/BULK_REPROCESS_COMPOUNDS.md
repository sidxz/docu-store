# Bulk Reprocess Compounds (admin action)

**Status:** implemented 2026-07-04. Motivated by the CSER/libdevice fix — the
existing corpus was ingested while GPU SMILES extraction was silently returning
0 compounds, so every page needs re-extraction once the fix ships.

## Goal

One admin trigger that re-runs CSER compound extraction across all artifacts in a
workspace, cleaning up stale/orphan compound data first.

## Key insight — the embed step is already automatic

The event cascade already does extract → save → re-embed idempotently:

1. `ExtractCompoundMentionsUseCase` runs CSER, `page.update_compound_mentions(...)`
   **replaces** the page's mentions, saves → emits `Page.CompoundMentionsUpdated`.
2. `pipeline_worker` handles that event → `TriggerSmilesEmbeddingUseCase` →
   `SmilesEmbeddingWorkflow` → `compound_qdrant_store.upsert_compound_embeddings`,
   which **deletes existing points for the page then upserts** with deterministic
   ids `uuid5(page_id:compound:idx)`.

So re-running extraction *is* re-embedding, per page, idempotently. The feature is
therefore mostly wiring + one purge method — not a new pipeline.

## What "cleanup first" actually protects against

Per-page delete-then-upsert only cleans points for the *current* page_id. It cannot
remove **orphan** points whose page_id no longer exists (old random-id pages, deleted
pages/artifacts). Compound points carry `workspace_id` and `artifact_id` in payload,
so a workspace-scoped delete removes orphans that the cascade can't.

## Design (lean — reuse the per-page workflow + cascade)

**Backend**
- `CompoundVectorStore.delete_compound_embeddings_for_workspace(workspace_id)` — new
  port method + Qdrant adapter impl (delete by `workspace_id` filter; best-effort,
  mirrors `delete_compound_embeddings_for_page`).
- `TriggerBulkReprocessCompoundsUseCase.execute(workspace_id)`:
  1. purge compound vectors for the workspace (best-effort — a failure here does not
     block extraction; the cascade still fixes current pages),
  2. `list_artifacts(workspace_id)` → `get_pages_by_artifact_ids(...)`,
  3. `start_compound_extraction_workflow(page_id)` per page.
  Returns `BulkWorkflowResponse` (reused; `targets` left empty).
- `POST /system/reprocess-compounds-all` (admin-only) — mirrors `/system/reembed-all`.
- DI registration mirrors `TriggerBulkReEmbedUseCase`.

**Frontend**
- `useReprocessCompounds()` in `hooks/use-health.ts` — POST the endpoint.
- A "Compound Re-extraction (CSER)" panel in the status page Admin Actions area,
  admin-gated, mirroring the re-embed panel. A confirm step guards it (heavy + wipes
  compound vectors before rebuild).

## Decisions

- **Reuse per-page `ExtractCompoundMentionsWorkflow` + cascade** rather than a new
  per-artifact batch workflow — least new code, reuses proven idempotent paths, and
  matches how extraction runs during normal ingestion. Cost: fires one workflow per
  page (many), and the re-embed depends on `pipeline_worker` running (it always is in
  prod — it is the normal ingestion path).
- **Purge scope = workspace, Qdrant only.** Matches the workspace-scoped endpoint;
  multi-tenant safe. Page aggregate mentions are left alone — re-extraction replaces
  them. (Points written with a null `workspace_id`, pre-workspace, would not match a
  workspace filter; not a concern on freshly-bootstrapped deployments.)

## Not doing (YAGNI)

- No throttling/batching of the fan-out (manual admin action; add only if worker
  over-subscription becomes a problem).
- No explicit second re-embed pass (the cascade covers it; a second pass would be
  redundant double work).
- No cross-workspace "reprocess everything" (workspace-scoped like re-embed-all).
