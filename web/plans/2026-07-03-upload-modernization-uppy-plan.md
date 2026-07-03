# Upload Modernization (Uppy v5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace the document upload page with an Uppy-v5-headless uploader that supports folder + 100s-of-files uploads, real per-file/overall progress, retry, and a clear "all files uploaded successfully" confirmation.

**Architecture:** `@uppy/core` + `@uppy/xhr-upload` drive the existing `POST /artifacts/upload` (no backend change). A `useDocumentUploader` hook constructs the Uppy engine; pure shadcn presentational components render file rows + a summary bar; the page wires Uppy state/events (via `@uppy/react` hooks) into those components. `react-dropzone` stays as the drop-region + folder-recursion + filter, feeding `File[]` into Uppy.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind v4, shadcn/ui, `react-dropzone` (existing), `@uppy/core` + `@uppy/xhr-upload` + `@uppy/react` (new, MIT).

**Spec:** `web/plans/2026-07-03-upload-modernization-uppy-design.md`

## Global Constraints

- **Frontend only.** Endpoint unchanged: `POST ${API_URL}/artifacts/upload`, multipart, one file per request. Fields: `file` (the file), `artifact_type`, `visibility`, optional `source_uri`.
- **Uppy v5 headless** — `@uppy/core` + `@uppy/xhr-upload` + `@uppy/react`. NO `@uppy/dashboard`, NO Uppy CSS. UI is 100% shadcn.
- **Uppy React hooks:** memoize with `const [uppy] = useState(() => new Uppy()...)`. `useUppyState(uppy, selector)` and `useUppyEvent(uppy, event, cb)` need **no** provider.
- **Accept:** `application/pdf` `.pdf`, `.pptx`, `.ppt`, `.doc`, `.docx`. **Max size:** `100_000_000` bytes. **Concurrency:** `UPLOAD_CONCURRENCY = 4`.
- **Auth:** `headers: () => getAuthzClient().getHeaders()` (per-request, so refreshed tokens are used on retry). `getAuthzClient` from `@/lib/auth` (same source the existing `useUploadArtifact` uses — verify import path there).
- **Meta:** `allowedMetaFields: ["artifact_type", "visibility", "source_uri"]`; set via `uppy.setMeta({...})` kept in sync with the batch controls.
- **Verify:** `cd web/apps/portal && pnpm lint` (tsc --noEmit) must pass. No frontend test framework — the gate is typecheck + a browser render via the playwright harness (both light/dark). A dev server runs on :15000 — do NOT start another; do NOT `pnpm build`.
- **Theme-correct colors:** any status color uses `text-*-600 dark:text-*-400` (light theme is real in this app).
- Commit per task on branch `upload-uppy` (already checked out), messages `feat(web): …`, ending with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## File structure

- `hooks/use-document-uploader.ts` (new) — Uppy engine + `addFiles` helper.
- `components/documents/UploadFileRow.tsx` (new) — one pure file row.
- `components/documents/UploadSummaryBar.tsx` (new) — pure summary/actions + completion banner.
- `components/documents/UploadDropzone.tsx` (new) — pure drop-region + browse-files + select-folder.
- `app/[workspace]/documents/upload/page.tsx` (rewrite) — integrates hook + components.
- `hooks/use-artifacts.ts` — retire `useUploadArtifact` only if the page was its sole caller (it is); leave the rest of the file intact.

---

### Task 1: `useDocumentUploader` hook + deps

**Files:**
- Modify: `web/apps/portal/package.json` (add deps) + `web/pnpm-lock.yaml`
- Create: `web/apps/portal/src/hooks/use-document-uploader.ts`

**Interfaces:**
- Produces: `useDocumentUploader(): { uppy: Uppy, addFiles(files: File[]): void }`. The Uppy instance is memoized and pre-configured with XHRUpload. `addFiles` maps `File[]` → `uppy.addFile(...)` attaching `meta.relativePath` (from react-dropzone's `file.path`, if any) and swallowing per-file restriction/duplicate throws.
- Consumes (existing): `API_URL` from `@/lib/constants`; `getAuthzClient` from `@/lib/auth` (confirm exact export used by `use-artifacts.ts`).

- [ ] **Step 1: Add dependencies**

Run: `cd /Users/sidx/workspace/docu-store/web/apps/portal && pnpm add @uppy/core @uppy/xhr-upload @uppy/react`
Expected: three deps added to `package.json`, lockfile updated, postinstall runs clean.

- [ ] **Step 2: Write the hook**

Create `web/apps/portal/src/hooks/use-document-uploader.ts`:

```typescript
"use client";

import { useState } from "react";
import Uppy from "@uppy/core";
import XHRUpload from "@uppy/xhr-upload";
import { API_URL } from "@/lib/constants";
import { getAuthzClient } from "@/lib/auth";

export const UPLOAD_CONCURRENCY = 4;
export const MAX_FILE_SIZE = 100_000_000;
export const ALLOWED_EXTENSIONS = [".pdf", ".pptx", ".ppt", ".doc", ".docx"];

/** Uppy engine for document uploads — headless (no Dashboard). The page renders
 *  the UI from `uppy` state via @uppy/react hooks; `addFiles` ingests the
 *  File[] that react-dropzone hands us (already accept/size-filtered). */
export function useDocumentUploader() {
  const [uppy] = useState(() =>
    new Uppy({
      autoProceed: false,
      restrictions: {
        maxFileSize: MAX_FILE_SIZE,
        allowedFileTypes: ALLOWED_EXTENSIONS,
      },
    }).use(XHRUpload, {
      endpoint: `${API_URL}/artifacts/upload`,
      method: "POST",
      fieldName: "file",
      formData: true,
      limit: UPLOAD_CONCURRENCY,
      timeout: 120_000,
      allowedMetaFields: ["artifact_type", "visibility", "source_uri"],
      headers: () => getAuthzClient().getHeaders() as Record<string, string>,
    }),
  );

  const addFiles = (files: File[]) => {
    for (const file of files) {
      try {
        uppy.addFile({
          name: file.name,
          type: file.type,
          data: file,
          // react-dropzone sets `.path` (relative folder path) on folder drops;
          // stash it for display + dedup across same-named files in subfolders.
          meta: { relativePath: (file as File & { path?: string }).path ?? file.name },
        });
      } catch {
        // Duplicate / restriction — Uppy emits an event the UI already surfaces.
      }
    }
  };

  return { uppy, addFiles };
}
```

- [ ] **Step 3: Typecheck**

Run: `cd /Users/sidx/workspace/docu-store/web/apps/portal && pnpm lint`
Expected: PASS. If `getAuthzClient` import path differs, match what `src/hooks/use-artifacts.ts` imports (grep it) before assuming.

- [ ] **Step 4: Commit**

```bash
git add web/apps/portal/package.json web/pnpm-lock.yaml web/apps/portal/src/hooks/use-document-uploader.ts
git commit -m "feat(web): useDocumentUploader hook (Uppy v5 engine)"
```

---

### Task 2: Pure presentational components

**Files:**
- Create: `web/apps/portal/src/components/documents/UploadFileRow.tsx`
- Create: `web/apps/portal/src/components/documents/UploadSummaryBar.tsx`
- Create: `web/apps/portal/src/components/documents/UploadDropzone.tsx`

**Interfaces (Produces — the page passes these props):**
- `UploadFileRow(props: { name: string; relativePath?: string; size: number; status: "queued"|"uploading"|"success"|"error"; progress: number; error?: string; onRetry?: () => void; onRemove?: () => void })`
- `UploadSummaryBar(props: { total: number; uploaded: number; failed: number; overallProgress: number; isUploading: boolean; isPaused: boolean; hasFailed: boolean; done: boolean; onUpload: () => void; onPauseResume: () => void; onRetryFailed: () => void; onCancel: () => void; onClearDone: () => void })`
- `UploadDropzone(props: { onFiles: (files: File[]) => void; onReject?: (count: number) => void; disabled?: boolean })` — renders the react-dropzone region + a "Browse files" and a "Select folder" (`webkitdirectory`) input, all funneling to `onFiles`; `onDropRejected` reports the count of skipped files via `onReject`.

- [ ] **Step 1: `UploadFileRow`**

Create `web/apps/portal/src/components/documents/UploadFileRow.tsx`:

```tsx
"use client";

import { FileText, CheckCircle2, XCircle, RotateCcw, X, Loader2 } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { formatFileSize } from "@/lib/utils";

interface Props {
  name: string;
  relativePath?: string;
  size: number;
  status: "queued" | "uploading" | "success" | "error";
  progress: number;
  error?: string;
  onRetry?: () => void;
  onRemove?: () => void;
}

export function UploadFileRow({ name, relativePath, size, status, progress, error, onRetry, onRemove }: Props) {
  return (
    <div className="flex items-center gap-3 px-3 py-2.5">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-sunken">
        {status === "success" ? (
          <CheckCircle2 className="size-4 text-ds-success" />
        ) : status === "error" ? (
          <XCircle className="size-4 text-ds-error" />
        ) : status === "uploading" ? (
          <Loader2 className="size-4 animate-spin text-accent-text" />
        ) : (
          <FileText className="size-4 text-text-muted" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <p className="truncate text-sm font-medium text-text-primary">{name}</p>
          <span className="shrink-0 text-xs text-text-muted">{formatFileSize(size)}</span>
        </div>
        {relativePath && relativePath !== name && (
          <p className="truncate text-[11px] text-text-muted">{relativePath}</p>
        )}
        {status === "uploading" && <Progress value={progress} className="mt-1.5 h-1" />}
        {status === "error" && error && (
          <p className="mt-0.5 truncate text-[11px] text-ds-error" title={error}>{error}</p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {status === "error" && onRetry && (
          <button type="button" onClick={onRetry} aria-label="Retry" className="rounded p-1 text-text-muted hover:text-text-secondary">
            <RotateCcw className="size-3.5" />
          </button>
        )}
        {status !== "uploading" && onRemove && (
          <button type="button" onClick={onRemove} aria-label="Remove" className="rounded p-1 text-text-muted hover:text-ds-error">
            <X className="size-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}
```

If `formatFileSize` is not exported from `web/apps/portal/src/lib/utils.ts`, move the copy currently defined inline in the upload page into `lib/utils.ts` and export it (single source), then import it here.

- [ ] **Step 2: `UploadSummaryBar`**

Create `web/apps/portal/src/components/documents/UploadSummaryBar.tsx`:

```tsx
"use client";

import { Upload, Pause, Play, RotateCcw, X, CheckCircle2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

interface Props {
  total: number;
  uploaded: number;
  failed: number;
  overallProgress: number;
  isUploading: boolean;
  isPaused: boolean;
  hasFailed: boolean;
  done: boolean; // all files reached a terminal state (success or error)
  onUpload: () => void;
  onPauseResume: () => void;
  onRetryFailed: () => void;
  onCancel: () => void;
  onClearDone: () => void;
}

export function UploadSummaryBar(p: Props) {
  if (p.done) {
    const allOk = p.failed === 0;
    return (
      <div className={`flex items-center justify-between gap-3 rounded-xl border p-4 ${allOk ? "border-ds-success/30 bg-ds-success/5" : "border-ds-warning/30 bg-ds-warning/5"}`}>
        <div className="flex items-center gap-2">
          {allOk ? <CheckCircle2 className="size-5 text-ds-success" /> : <AlertTriangle className="size-5 text-ds-warning" />}
          <span className="text-sm font-medium text-text-primary">
            {allOk ? `All ${p.uploaded} files uploaded successfully` : `${p.uploaded} uploaded, ${p.failed} failed`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {p.hasFailed && (
            <Button size="sm" variant="outline" onClick={p.onRetryFailed}><RotateCcw className="size-4" />Retry failed</Button>
          )}
          <Button size="sm" variant="ghost" onClick={p.onClearDone}>Clear</Button>
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-border-default bg-surface-elevated p-4">
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="text-text-secondary">
          {p.uploaded}/{p.total} uploaded{p.failed > 0 ? ` · ${p.failed} failed` : ""}
        </span>
        <div className="flex items-center gap-2">
          {p.isUploading ? (
            <Button size="sm" variant="outline" onClick={p.onPauseResume}>
              {p.isPaused ? <><Play className="size-4" />Resume</> : <><Pause className="size-4" />Pause</>}
            </Button>
          ) : (
            <Button size="sm" onClick={p.onUpload} disabled={p.total === 0}><Upload className="size-4" />Upload {p.total > 0 ? `${p.total} files` : ""}</Button>
          )}
          {p.isUploading && (
            <Button size="sm" variant="ghost" onClick={p.onCancel}><X className="size-4" />Cancel</Button>
          )}
        </div>
      </div>
      <Progress value={p.overallProgress} className="h-1.5" />
    </div>
  );
}
```

- [ ] **Step 3: `UploadDropzone`**

Create `web/apps/portal/src/components/documents/UploadDropzone.tsx`:

```tsx
"use client";

import { useRef } from "react";
import { useDropzone, type Accept } from "react-dropzone";
import { UploadCloud, FolderOpen, FilePlus2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const ACCEPT: Accept = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
  "application/vnd.ms-powerpoint": [".ppt"],
  "application/msword": [".doc"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
};
const MAX_FILE_SIZE = 100_000_000;

export function UploadDropzone({ onFiles, onReject, disabled }: { onFiles: (files: File[]) => void; onReject?: (count: number) => void; disabled?: boolean }) {
  const folderRef = useRef<HTMLInputElement>(null);
  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop: (accepted) => accepted.length && onFiles(accepted),
    onDropRejected: (rejections) => onReject?.(rejections.length),
    accept: ACCEPT,
    maxSize: MAX_FILE_SIZE,
    multiple: true,
    noClick: true,
    disabled,
  });

  return (
    <div
      {...getRootProps()}
      className={cn(
        "flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 text-center transition-colors",
        isDragActive ? "border-primary bg-accent-light" : "border-border-default",
      )}
    >
      <input {...getInputProps()} />
      {/* webkitdirectory input for folder selection — filtered by the same accept in the parent's onFiles */}
      <input
        ref={folderRef}
        type="file"
        // @ts-expect-error non-standard attributes for folder selection
        webkitdirectory=""
        directory=""
        multiple
        hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          if (files.length) onFiles(files);
          e.target.value = "";
        }}
      />
      <div className="mb-3 flex size-12 items-center justify-center rounded-xl bg-accent-light">
        <UploadCloud className="size-6 text-accent-text" />
      </div>
      <p className="text-sm font-medium text-text-primary">Drag files or a folder here</p>
      <p className="mt-1 text-xs text-text-muted">PDF, PPT, PPTX, DOC, DOCX · up to 100 MB each</p>
      <div className="mt-4 flex gap-2">
        <Button type="button" variant="outline" size="sm" onClick={open} disabled={disabled}>
          <FilePlus2 className="size-4" />Browse files
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={() => folderRef.current?.click()} disabled={disabled}>
          <FolderOpen className="size-4" />Select folder
        </Button>
      </div>
    </div>
  );
}
```

Note: the folder input bypasses react-dropzone's accept filter, so the parent's `onFiles` (Task 3) must filter folder-selected files to the accepted extensions before adding.

- [ ] **Step 4: Typecheck + render the components with mock props**

Run: `cd /Users/sidx/workspace/docu-store/web/apps/portal && pnpm lint`
Expected: PASS. Then browser-render a scratch page mounting `UploadFileRow` (one row per status: queued/uploading/success/error) and `UploadSummaryBar` (in-progress and done-with-failures states) with mock props, both light+dark, via the playwright harness; confirm layout + theme-correct colors. Delete the scratch page before committing.

- [ ] **Step 5: Commit**

```bash
git add web/apps/portal/src/components/documents/UploadFileRow.tsx web/apps/portal/src/components/documents/UploadSummaryBar.tsx web/apps/portal/src/components/documents/UploadDropzone.tsx web/apps/portal/src/lib/utils.ts
git commit -m "feat(web): upload UI components (row, summary bar, dropzone)"
```

---

### Task 3: Rewrite the upload page (integration)

**Files:**
- Modify: `web/apps/portal/src/app/[workspace]/documents/upload/page.tsx` (rewrite the file-upload UI)
- Modify: `web/apps/portal/src/hooks/use-artifacts.ts` (remove `useUploadArtifact` — the page is its only caller; leave the rest)

**Interfaces:**
- Consumes: `useDocumentUploader()` (Task 1); `UploadDropzone`/`UploadFileRow`/`UploadSummaryBar` (Task 2); Uppy React hooks `useUppyState`/`useUppyEvent` from `@uppy/react`; existing `useScopeStore`, `ARTIFACT_TYPES`, `PageHeader`, `Select`, `ScrollArea`.

- [ ] **Step 1: Rewrite the page**

Replace the body of `page.tsx`. Key wiring (write the full component; the essentials):

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { BarChart3, FileUp } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useUppyState } from "@uppy/react";
import { useDocumentUploader, ALLOWED_EXTENSIONS } from "@/hooks/use-document-uploader";
import { useScopeStore } from "@/lib/stores/scope-store";
import { UploadDropzone } from "@/components/documents/UploadDropzone";
import { UploadFileRow } from "@/components/documents/UploadFileRow";
import { UploadSummaryBar } from "@/components/documents/UploadSummaryBar";

const ARTIFACT_TYPES = [
  { label: "Research Article", value: "RESEARCH_ARTICLE" },
  { label: "Scientific Document", value: "SCIENTIFIC_DOCUMENT" },
  { label: "Scientific Presentation", value: "SCIENTIFIC_PRESENTATION" },
  { label: "Generic Presentation", value: "GENERIC_PRESENTATION" },
  { label: "Disclosure Document", value: "DISCLOSURE_DOCUMENT" },
  { label: "Minutes of Meeting", value: "MINUTE_OF_MEETING" },
  { label: "Unclassified", value: "UNCLASSIFIED" },
];

export default function UploadPage() {
  useParams<{ workspace: string }>();
  const { uppy, addFiles } = useDocumentUploader();
  const [artifactType, setArtifactType] = useState("SCIENTIFIC_DOCUMENT");
  const defaultScope = useScopeStore((s) => s.defaultScope);
  const [isUploading, setIsUploading] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [skipped, setSkipped] = useState(0); // count of files filtered out (wrong type / too big)

  // keep batch meta in sync with the controls
  useEffect(() => {
    uppy.setMeta({ artifact_type: artifactType, visibility: defaultScope });
  }, [uppy, artifactType, defaultScope]);

  // reflect upload lifecycle
  useEffect(() => {
    const onUpload = () => setIsUploading(true);
    const onComplete = () => { setIsUploading(false); setIsPaused(false); };
    uppy.on("upload", onUpload);
    uppy.on("complete", onComplete);
    return () => { uppy.off("upload", onUpload); uppy.off("complete", onComplete); };
  }, [uppy]);

  const files = useUppyState(uppy, (s) => s.files);
  const totalProgress = useUppyState(uppy, (s) => s.totalProgress);
  const list = useMemo(() => Object.values(files), [files]);

  const rows = list.map((f) => {
    const status: "queued" | "uploading" | "success" | "error" =
      f.error ? "error" : f.progress?.uploadComplete ? "success" : f.progress?.uploadStarted ? "uploading" : "queued";
    return {
      id: f.id,
      name: f.name ?? f.meta?.name ?? "file",
      relativePath: typeof f.meta?.relativePath === "string" ? f.meta.relativePath : undefined,
      size: f.size ?? 0,
      status,
      progress: f.progress?.percentage ?? 0,
      error: typeof f.error === "string" ? f.error : undefined,
    };
  });

  const uploaded = rows.filter((r) => r.status === "success").length;
  const failed = rows.filter((r) => r.status === "error").length;
  const done = list.length > 0 && !isUploading && rows.every((r) => r.status === "success" || r.status === "error");

  // folder input can include non-accepted files — filter to accepted extensions
  const handleFiles = (incoming: File[]) => {
    const ok = incoming.filter((f) => ALLOWED_EXTENSIONS.some((e) => f.name.toLowerCase().endsWith(e)));
    if (ok.length < incoming.length) setSkipped((s) => s + (incoming.length - ok.length));
    addFiles(ok);
  };

  return (
    <div>
      <PageHeader icon={FileUp} title="Upload documents" subtitle="Drag a folder or files — they upload in parallel with per-file status." />
      <div className="mx-auto max-w-3xl space-y-4">
        <div className="flex items-center gap-3">
          <Select value={artifactType} onValueChange={setArtifactType}>
            <SelectTrigger className="w-64"><SelectValue /></SelectTrigger>
            <SelectContent>
              {ARTIFACT_TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <span className="text-xs text-text-muted">Applies to all files in this batch · visibility: {defaultScope}</span>
        </div>

        <UploadDropzone onFiles={handleFiles} onReject={(n) => setSkipped((s) => s + n)} disabled={isUploading} />

        {skipped > 0 && (
          <Alert>
            <AlertDescription className="flex items-center justify-between gap-3">
              <span>{skipped} file{skipped === 1 ? "" : "s"} skipped — unsupported type or over 100 MB.</span>
              <button type="button" onClick={() => setSkipped(0)} className="shrink-0 text-xs text-text-muted hover:text-text-secondary">Dismiss</button>
            </AlertDescription>
          </Alert>
        )}

        {list.length > 0 && (
          <>
            <UploadSummaryBar
              total={list.length}
              uploaded={uploaded}
              failed={failed}
              overallProgress={totalProgress}
              isUploading={isUploading}
              isPaused={isPaused}
              hasFailed={failed > 0}
              done={done}
              onUpload={() => uppy.upload()}
              onPauseResume={() => { if (isPaused) { uppy.resumeAll(); setIsPaused(false); } else { uppy.pauseAll(); setIsPaused(true); } }}
              onRetryFailed={() => uppy.retryAll()}
              onCancel={() => uppy.cancelAll()}
              onClearDone={() => list.filter((f) => f.progress?.uploadComplete || f.error).forEach((f) => uppy.removeFile(f.id))}
            />
            <div className="rounded-xl border border-border-default bg-surface-elevated">
              <ScrollArea className="max-h-[50vh]">
                <div className="divide-y divide-border-subtle">
                  {rows.map((r) => (
                    <UploadFileRow
                      key={r.id}
                      name={r.name}
                      relativePath={r.relativePath}
                      size={r.size}
                      status={r.status}
                      progress={r.progress}
                      error={r.error}
                      onRetry={r.status === "error" ? () => uppy.retryUpload(r.id) : undefined}
                      onRemove={() => uppy.removeFile(r.id)}
                    />
                  ))}
                </div>
              </ScrollArea>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
```

Adjust exact Uppy file-state field names (`progress.uploadComplete`, `progress.uploadStarted`, `progress.percentage`, `f.error`) to the installed `@uppy/core` types — hover/inspect the `UppyFile` type; the fields above are the v5 shape but verify against the installed `.d.ts` and fix any mismatch the typecheck flags.

- [ ] **Step 2: Remove the dead hook**

In `web/apps/portal/src/hooks/use-artifacts.ts`, delete the `useUploadArtifact` export and any now-unused imports it alone used (`ApiError`, `getAuthzClient`, `API_URL`, `useAnalytics`) — but only if nothing else in the file uses them (grep first). Leave every other export intact.

- [ ] **Step 3: Typecheck**

Run: `cd /Users/sidx/workspace/docu-store/web/apps/portal && pnpm lint`
Expected: PASS.

- [ ] **Step 4: Browser-verify the full flow**

Because the real endpoint needs auth, verify against a stub: temporarily point the hook's `endpoint` at a local mock that returns 201 for most files and 500 for one (or intercept via Playwright's `route` to fulfill/abort). Drive `/`+`documents/upload` in the harness and confirm, in light and dark:
1. Dragging a folder of mixed files → only accepted types queue (rejects excluded), each shows queued → uploading (progress) → ✓.
2. The forced-500 file shows an error row with a working per-row Retry and the summary shows "N uploaded, 1 failed" with "Retry failed".
3. All-success run resolves to the green "All N files uploaded successfully" banner.
Revert the stub before committing. Capture screenshots.

- [ ] **Step 5: Commit**

```bash
git add "web/apps/portal/src/app/[workspace]/documents/upload/page.tsx" web/apps/portal/src/hooks/use-artifacts.ts
git commit -m "feat(web): Uppy-powered upload page (folder, progress, retry, success confirmation)"
```

---

## Notes for the implementer

- Do NOT import any `@uppy/*/dist/style.css` — this is headless; all styling is shadcn.
- `getAuthzClient().getHeaders()` returns the auth headers object; cast to `Record<string,string>` for XHRUpload's `headers`. Confirm the exact import (`@/lib/auth` vs elsewhere) against `use-artifacts.ts`.
- The design's out-of-scope items (live processing status, Companion/remote sources, tus/resumable) stay out — do not add them.
- **`source_uri` deviation:** the old single-file page had an optional `source_uri` (provenance URL) input. A single URL field makes no sense across a folder of 100s, so the batch uploader **omits it from the UI**. The endpoint still accepts it and `allowedMetaFields` still includes it, so it can be re-added later (e.g., only in a single-file mode) with no backend change. This deviates from the spec's "source_uri path stays untouched" — surfaced to the user at handoff; do not silently keep or drop it against their wishes.
