"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { FileUp } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useUppyState, useUppyEvent } from "@uppy/react";
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

  // reflect upload lifecycle — useUppyEvent owns subscribe/cleanup internally.
  // Stable callback identities so it doesn't resubscribe on every render
  // (files state, and thus this component, re-renders on every progress tick).
  const onUploadStart = useCallback(() => setIsUploading(true), []);
  const onUploadComplete = useCallback(() => {
    setIsUploading(false);
    setIsPaused(false);
  }, []);
  useUppyEvent(uppy, "upload", onUploadStart);
  useUppyEvent(uppy, "complete", onUploadComplete);

  const files = useUppyState(uppy, (s) => s.files);
  const totalProgress = useUppyState(uppy, (s) => s.totalProgress);
  const list = useMemo(() => Object.values(files), [files]);

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
          <Select value={artifactType} onValueChange={setArtifactType}>
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
          <span className="text-xs text-text-muted">
            Applies to all files in this batch · visibility: {defaultScope}
          </span>
        </div>

        <UploadDropzone
          onFiles={handleFiles}
          onReject={(n) => setSkipped((s) => s + n)}
          disabled={isUploading}
        />

        {skipped > 0 && (
          <Alert>
            <AlertDescription className="flex items-center justify-between gap-3">
              <span>
                {skipped} file{skipped === 1 ? "" : "s"} skipped — unsupported type or over 100
                MB.
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
              isPaused={isPaused}
              hasFailed={failed > 0}
              done={done}
              onUpload={() => uppy.upload()}
              onPauseResume={() => {
                if (isPaused) {
                  uppy.resumeAll();
                  setIsPaused(false);
                } else {
                  uppy.pauseAll();
                  setIsPaused(true);
                }
              }}
              onRetryFailed={() => uppy.retryAll()}
              onCancel={() => uppy.cancelAll()}
              onClearDone={() =>
                list
                  .filter((f) => f.progress.uploadComplete || f.error)
                  .forEach((f) => uppy.removeFile(f.id))
              }
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
