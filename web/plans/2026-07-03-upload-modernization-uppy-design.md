# Upload modernization (Uppy v5, headless) — design

**Date:** 2026-07-03
**Branch:** `main` (this session's work merged there)
**Status:** approved (design), pending spec review

## Goal

Modernize the document upload experience so a user can drop a **folder or 100s
of files**, watch **real per-file + overall progress**, and get a clear,
trustworthy **confirmation that every file uploaded successfully** (with easy
retry of any that failed). Frontend-only; no backend change.

The core intent: *"confirm that all files uploaded successfully."* The UI is
built around that — reliable per-file success/failure and retry, not pipeline
tracking.

## Non-goals (v1)

- Live server-side processing status (parse/embed pipeline) — stays on the
  existing Documents/Status pages.
- Uppy Companion / remote-source imports (Google Drive, Dropbox).
- Resumable / chunked (tus) uploads — would require backend support.

## Stack

**Uppy v5, headless** (all MIT-licensed), no Uppy Dashboard, no Uppy CSS:
- `@uppy/core` — upload engine (queue, per-file state, events).
- `@uppy/xhr-upload` — posts each file to the existing `POST /artifacts/upload`
  via XHR: per-file byte progress, bounded concurrency (`limit`), built-in
  retry/backoff.
- `@uppy/react` — v5 React hooks (`useUppyState`, `useUppyEvent`) to drive the
  shadcn UI from Uppy state.
- Keep **`react-dropzone`** (already a dependency) solely as the drop-region +
  folder-recursion + accept/size filter. Accepted `File[]` are handed to
  `uppy.addFiles()`. Clean split: dropzone *gets* files, Uppy *uploads* them.

No backend change: same endpoint, same multipart fields. `artifact_type` and
`visibility` are chosen once for the batch and attached as each Uppy file's
`meta` (xhr-upload sends meta as form fields). Auth via a per-request function
`headers: () => getAuthzClient().getHeaders()` so refreshed tokens are used on
retries.

## Entry points (all feed one queue)

1. **Drag** files or a folder onto the dropzone — react-dropzone recurses
   dropped directories.
2. **Browse files** — multi-select file input (react-dropzone `getInputProps`).
3. **Select folder** — a separate `webkitDirectory` input (the capability
   missing today). Its `FileList` is filtered through the same accept/size
   rules, then added to Uppy.

## Behavior

- **Bounded concurrency:** `xhr-upload` `limit: 4` (config constant) — faster
  than today's strictly-sequential loop, still gentle on the API (upload =
  blob write + event; heavy work is downstream in Temporal, gated at 5/2).
- **Retry:** Uppy built-in retry with backoff, plus explicit "Retry failed"
  (`uppy.retryAll()`), per-file remove/cancel, and pause/resume
  (`uppy.pauseAll()`/`resumeAll()`).
- **Filtering:** react-dropzone enforces accept (`application/pdf`, `.pptx`,
  `.ppt`, `.doc`, `.docx`) and 100 MB/file. Rejected files are listed with the
  reason and never enter the upload queue. Uppy `restrictions` mirror these as
  a second guard.

## UI (shadcn, informative)

- **Dropzone** — three entry points + a line stating accepted types and the
  100 MB cap; active/hover drag state.
- **Batch controls** (apply to all files): artifact-type `Select` +
  workspace/private visibility toggle.
- **File list** (scrollable; virtualize only if it becomes a perf issue):
  per row `[type icon] filename (relative folder path if from a folder) · size
  · [progress bar → ✓ success / ✗ error + reason] · [retry | remove]`. States:
  `queued`, `uploading (N%)`, `success`, `error(message)`, `rejected(reason)`.
- **Summary bar** — the confirmation payoff:
  `▓▓▓ 62% · 84/210 uploaded · 3 failed · 12 MB/s · ~ETA` with actions
  **Pause/Resume · Retry failed · Cancel · Clear completed**. On completion it
  resolves to a clear banner:
  - **✅ All N files uploaded successfully**, or
  - **⚠️ M uploaded, K failed → [Retry failed]**.
- Single-file upload behaves consistently within the list (no special-case
  navigation required); a link to the uploaded document(s) is offered on
  success.

## Error handling

- Per-file upload error (`upload-error`) → row shows the server message + Retry.
- Auth 401 → the `headers` function returns fresh tokens on the retry attempt.
- Network drop → Uppy auto-retries per its backoff, then surfaces as a failed
  row (retryable).
- Type/size rejection → listed with the reason, excluded from the queue and the
  success count.
- The success/failure counts in the summary are the single source of truth for
  "did everything land."

## Files (frontend only)

- **Rewrite:** `web/apps/portal/src/app/[workspace]/documents/upload/page.tsx`
  (dropzone + batch controls + file list + summary; uses the hook + Uppy React
  hooks). The existing **URL/source-based** creation path (`source_uri`) is
  preserved unchanged — Uppy replaces only the *file* upload path.
- **Add:** `hooks/use-document-uploader.ts` — constructs and memoizes the Uppy
  instance (`@uppy/core` + `@uppy/xhr-upload`) with endpoint, headers, meta,
  `limit`, restrictions, retry; exposes the instance + derived state helpers.
- **Add:** small components `components/documents/UploadDropzone.tsx`,
  `UploadFileRow.tsx`, `UploadSummaryBar.tsx` (keep the page thin).
- **Check:** other callers of `useUploadArtifact`; keep it if the `source_uri`
  path or another feature still needs it, otherwise retire the file-upload
  branch.
- **Deps:** add `@uppy/core`, `@uppy/xhr-upload`, `@uppy/react` (pnpm, portal).

## Verification

Typecheck (`pnpm lint`). Browser-verify the UI states in both themes with the
playwright harness: (1) drag a folder of mixed files → recursion + accept
filter + queue + progress + per-file ✓ + "all uploaded" banner; (2) an
oversized/wrong-type file → rejected with reason, excluded from the count;
(3) a forced upload failure → error row + working "Retry failed". Because the
real endpoint needs auth, drive the UI against a stub endpoint (or Uppy pointed
at a mock) for the failure/success paths.
