"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { FileUp } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/ui/PageHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useUppyState, useUppyEvent } from "@uppy/react";
import type { Meta, UploadResult } from "@uppy/core";
import { useDocumentUploader, ALLOWED_EXTENSIONS } from "@/hooks/use-document-uploader";
import { useAnalytics } from "@/hooks/use-analytics";
import { queryKeys } from "@/lib/query-keys";
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
  const { uppy, addFiles } = useDocumentUploader();
  const { workspace } = useParams<{ workspace: string }>();
  const queryClient = useQueryClient();
  const { trackEvent } = useAnalytics();
  const [artifactType, setArtifactType] = useState("SCIENTIFIC_DOCUMENT");
  const [sourceUri, setSourceUri] = useState("");
  const defaultScope = useScopeStore((s) => s.defaultScope);
  const [skipped, setSkipped] = useState(0); // files filtered out (wrong type / too big / duplicate)

  // keep batch meta in sync with the controls
  useEffect(() => {
    const uri = sourceUri.trim();
    uppy.setMeta({ artifact_type: artifactType, visibility: defaultScope, source_uri: uri });
    // xhr-upload appends every allowedMetaFields entry verbatim (no presence
    // check), so an empty source_uri would POST ""/"undefined" and the backend
    // stores it as-is (source_uri: str | None, no empty→None coercion). Toggle
    // the field in allowedMetaFields instead — setMeta can only merge, never unset.
    uppy.getPlugin("XHRUpload")?.setOptions({
      allowedMetaFields: uri
        ? ["artifact_type", "visibility", "source_uri"]
        : ["artifact_type", "visibility"],
    });
  }, [uppy, artifactType, defaultScope, sourceUri]);

  // Derived, not mirrored: currentUploads empties when #runUpload finishes —
  // upload(), retryAll() and per-row retryUpload() all route through it, and
  // cancelAll()/removeFiles() drop emptied uploads too.
  const isUploading = useUppyState(uppy, (s) => Object.keys(s.currentUploads).length > 0);

  // Stable callback identities so useUppyEvent doesn't resubscribe on every render
  // (files state, and thus this component, re-renders on every progress tick).
  const onRestrictionFailed = useCallback(() => setSkipped((s) => s + 1), []);
  useUppyEvent(uppy, "restriction-failed", onRestrictionFailed);

  const onComplete = useCallback(
    (result: UploadResult<Meta, Record<string, never>>) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.artifacts.all });
      const ext = (name?: string) => name?.split(".").pop()?.toLowerCase() ?? "unknown";
      for (const f of result.successful ?? []) {
        trackEvent("document_uploaded", {
          file_count: 1,
          file_type: ext(f.name),
          file_size_kb: Math.round((f.size ?? 0) / 1024),
        });
      }
      // New uploads start processing immediately — refresh the topbar badge.
      queryClient.invalidateQueries({ queryKey: queryKeys.artifacts.processing() });
      for (const f of result.failed ?? []) {
        trackEvent("upload_failed", {
          file_type: ext(f.name),
          file_size_kb: Math.round((f.size ?? 0) / 1024),
        });
      }
    },
    [queryClient, trackEvent],
  );
  useUppyEvent(uppy, "complete", onComplete);

  // Files that landed before a mid-batch navigation (which cancels the rest)
  // should still show up in the documents list.
  useEffect(
    () => () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.artifacts.all });
    },
    [queryClient],
  );

  const files = useUppyState(uppy, (s) => s.files);
  const totalProgress = useUppyState(uppy, (s) => s.totalProgress);
  const list = useMemo(() => Object.values(files), [files]);

  const retryFile = useCallback(
    (id: string) => {
      uppy.retryUpload(id);
    },
    [uppy],
  );
  const removeFile = useCallback(
    (id: string) => {
      uppy.removeFile(id);
    },
    [uppy],
  );

  const rows = list.map((f) => {
    const status: "queued" | "uploading" | "success" | "error" = f.error
      ? "error"
      : f.progress.uploadComplete
        ? "success"
        : f.progress.uploadStarted
          ? "uploading"
          : "queued";
    return {
      id: f.id,
      name: f.name,
      relativePath: f.meta.relativePath,
      size: f.size ?? 0,
      status,
      progress: f.progress.percentage ?? 0,
      error: f.error ?? undefined,
    };
  });

  const uploaded = rows.filter((r) => r.status === "success").length;
  const failed = rows.filter((r) => r.status === "error").length;
  const done =
    list.length > 0 &&
    !isUploading &&
    rows.every((r) => r.status === "success" || r.status === "error");

  // folder input can include non-accepted files — filter to accepted extensions
  const handleFiles = (incoming: File[]) => {
    const ok = incoming.filter((f) =>
      ALLOWED_EXTENSIONS.some((e) => f.name.toLowerCase().endsWith(e)),
    );
    if (ok.length < incoming.length) setSkipped((s) => s + (incoming.length - ok.length));
    addFiles(ok);
  };

  return (
    <div>
      <PageHeader
        icon={FileUp}
        title="Upload documents"
        subtitle="Drag a folder or files — they upload in parallel with per-file status."
      />
      <div className="mx-auto max-w-3xl space-y-4">
        <div className="flex items-center gap-3">
          <Select value={artifactType} onValueChange={setArtifactType} disabled={isUploading}>
            <SelectTrigger className="w-64">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ARTIFACT_TYPES.map((t) => (
                <SelectItem key={t.value} value={t.value}>
                  {t.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <label className="flex flex-1 items-center gap-2">
            <span className="shrink-0 text-xs text-text-muted">Source URI (optional)</span>
            <Input
              value={sourceUri}
              onChange={(e) => setSourceUri(e.target.value)}
              placeholder="https://..."
              disabled={isUploading}
              className="h-8 flex-1"
            />
          </label>
        </div>
        <p className="text-xs text-text-muted">
          Applies to all files in this batch · visibility: {defaultScope}
        </p>

        <UploadDropzone
          onFiles={handleFiles}
          onReject={(n) => setSkipped((s) => s + n)}
          disabled={isUploading}
        />

        {skipped > 0 && (
          <Alert>
            <AlertDescription className="flex items-center justify-between gap-3">
              <span>
                {skipped} file{skipped === 1 ? "" : "s"} skipped — unsupported type, over 100 MB,
                or already added.
              </span>
              <button
                type="button"
                onClick={() => setSkipped(0)}
                className="shrink-0 text-xs text-text-muted hover:text-text-secondary"
              >
                Dismiss
              </button>
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
              done={done}
              documentsHref={`/${workspace}/documents`}
              onUpload={() => uppy.upload()}
              onRetryFailed={() => uppy.retryAll()}
              onCancel={() => uppy.cancelAll()}
              onClearDone={() =>
                uppy.removeFiles(
                  list.filter((f) => f.progress.uploadComplete || f.error).map((f) => f.id),
                )
              }
            />
            <div className="rounded-xl border border-border-default bg-surface-elevated">
              <ScrollArea className="max-h-[50vh]">
                <div className="divide-y divide-border-subtle">
                  {rows.map((r) => (
                    <UploadFileRow
                      key={r.id}
                      id={r.id}
                      name={r.name}
                      relativePath={r.relativePath}
                      size={r.size}
                      status={r.status}
                      progress={r.progress}
                      error={r.error}
                      onRetry={retryFile}
                      onRemove={removeFile}
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
