"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { useDropzone, type Accept, type FileRejection } from "react-dropzone";
import { toast } from "sonner";
import {
  Upload,
  UploadCloud,
  ArrowLeft,
  Check,
  X,
  Loader2,
  AlertCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Progress } from "@/components/ui/progress";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { useUploadArtifact } from "@/hooks/use-artifacts";
import { useScopeStore } from "@/lib/stores/scope-store";
import { cn } from "@/lib/utils";

const ARTIFACT_TYPES = [
  { label: "Research Article", value: "RESEARCH_ARTICLE" },
  { label: "Scientific Document", value: "SCIENTIFIC_DOCUMENT" },
  { label: "Scientific Presentation", value: "SCIENTIFIC_PRESENTATION" },
  { label: "Generic Presentation", value: "GENERIC_PRESENTATION" },
  { label: "Disclosure Document", value: "DISCLOSURE_DOCUMENT" },
  { label: "Minutes of Meeting", value: "MINUTE_OF_MEETING" },
  { label: "Unclassified", value: "UNCLASSIFIED" },
];

const ACCEPT: Accept = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
  "application/vnd.ms-powerpoint": [".ppt"],
  "application/msword": [".doc"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
};

const MAX_FILE_SIZE = 100_000_000;

type FileStatus = "pending" | "uploading" | "success" | "error";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes;
  let i = -1;
  do {
    value /= 1024;
    i++;
  } while (value >= 1024 && i < units.length - 1);
  return `${value.toFixed(1)} ${units[i]}`;
}

export default function UploadPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const router = useRouter();
  const uploadMutation = useUploadArtifact();
  const { defaultScope } = useScopeStore();

  const [artifactType, setArtifactType] = useState("RESEARCH_ARTICLE");
  const [sourceUri, setSourceUri] = useState("");
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [fileStatuses, setFileStatuses] = useState<Record<string, FileStatus>>({});
  const [isUploading, setIsUploading] = useState(false);

  const busy = isUploading || uploadMutation.isPending;
  const isBatch = Object.keys(fileStatuses).length > 1;

  const handleUpload = useCallback(
    async (files: File[]) => {
      if (!files.length) return;

      // Single file — keep original behavior
      if (files.length === 1) {
        const file = files[0];
        try {
          const result = await uploadMutation.mutateAsync({
            file,
            artifactType,
            sourceUri: sourceUri || undefined,
            visibility: defaultScope,
          });
          router.push(`/${workspace}/documents/${result.artifact_id}`);
        } catch {
          // Error shown via uploadMutation.error
        }
        return;
      }

      // Multiple files — sequential upload with per-file status
      setIsUploading(true);
      const statuses: Record<string, FileStatus> = {};
      for (const f of files) statuses[f.name] = "pending";
      setFileStatuses({ ...statuses });

      for (const file of files) {
        setFileStatuses((prev) => ({ ...prev, [file.name]: "uploading" }));
        try {
          await uploadMutation.mutateAsync({
            file,
            artifactType,
            sourceUri: sourceUri || undefined,
            visibility: defaultScope,
          });
          setFileStatuses((prev) => ({ ...prev, [file.name]: "success" }));
        } catch {
          setFileStatuses((prev) => ({ ...prev, [file.name]: "error" }));
        }
      }

      setIsUploading(false);
    },
    [artifactType, sourceUri, defaultScope, uploadMutation, router, workspace],
  );

  const onDrop = useCallback((accepted: File[]) => {
    setPendingFiles((prev) => [...prev, ...accepted]);
  }, []);

  const onDropRejected = useCallback((rejections: FileRejection[]) => {
    for (const r of rejections) {
      toast.error(r.file.name, {
        description: r.errors[0]?.message ?? "File rejected",
      });
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    onDropRejected,
    accept: ACCEPT,
    maxSize: MAX_FILE_SIZE,
    multiple: true,
    disabled: busy,
  });

  // ponytail: upload goes through fetch (see useUploadArtifact), which has no
  // byte-level progress events — this shows a fixed in-flight fill, not real
  // percent. Switch the mutation to XHR/axios with onUploadProgress if real
  // per-file progress is ever needed.
  const statusFor = (file: File): FileStatus => {
    if (fileStatuses[file.name]) return fileStatuses[file.name];
    if (!isBatch && uploadMutation.isPending) return "uploading";
    if (!isBatch && uploadMutation.isError) return "error";
    if (!isBatch && uploadMutation.isSuccess) return "success";
    return "pending";
  };

  const doneCount = Object.values(fileStatuses).filter(
    (s) => s === "success" || s === "error",
  ).length;
  const totalCount = Object.keys(fileStatuses).length;
  const allDone = isBatch && doneCount === totalCount && !isUploading;

  return (
    <div>
      <Button
        variant="ghost"
        onClick={() => router.push(`/${workspace}/documents`)}
        className="mb-4"
      >
        <ArrowLeft className="size-3.5" />
        Documents
      </Button>

      <PageHeader
        icon={Upload}
        title="Upload Documents"
        subtitle="Upload one or more documents for automated analysis and extraction"
      />

      <Card className="max-w-2xl">
        <div className="space-y-6">
          <div>
            <label className="mb-2 block text-sm font-medium text-text-primary">
              Document Type
            </label>
            <Select value={artifactType} onValueChange={setArtifactType} disabled={busy}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ARTIFACT_TYPES.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-text-primary">
              Source URI
              <span className="ml-1 text-text-muted font-normal">(optional)</span>
            </label>
            <Input
              value={sourceUri}
              onChange={(e) => setSourceUri(e.target.value)}
              placeholder="https://..."
              className="w-full"
              disabled={busy}
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-text-primary">
              Files
            </label>
            <div
              {...getRootProps()}
              className={cn(
                "flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border-default bg-surface-sunken px-6 py-10 text-center transition-colors cursor-pointer",
                isDragActive && "border-primary bg-accent",
                busy && "cursor-not-allowed opacity-60",
              )}
            >
              <input {...getInputProps()} />
              <UploadCloud className="size-8 text-text-muted" />
              <p className="text-sm text-text-secondary">
                Drag & drop files here, or click to browse
              </p>
              <p className="text-xs text-text-muted">
                PDF, PPTX, DOC, DOCX up to 100MB each
              </p>
            </div>

            {pendingFiles.length > 0 && (
              <div className="mt-3 space-y-2">
                <div className="divide-y divide-border-default rounded-lg border border-border-default">
                  {pendingFiles.map((file, idx) => {
                    const status = statusFor(file);
                    return (
                      <div
                        key={`${file.name}-${idx}`}
                        className="flex items-center gap-3 px-3 py-2 text-sm"
                      >
                        {status === "pending" && (
                          <span className="h-4 w-4 shrink-0 rounded-full border-2 border-border-default" />
                        )}
                        {status === "uploading" && (
                          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
                        )}
                        {status === "success" && (
                          <Check className="h-4 w-4 shrink-0 text-ds-success" />
                        )}
                        {status === "error" && (
                          <X className="h-4 w-4 shrink-0 text-destructive" />
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-text-primary">{file.name}</p>
                          <p className="text-xs text-text-muted">
                            {formatFileSize(file.size)}
                          </p>
                          {status === "uploading" && (
                            <Progress value={60} className="mt-1 h-1" />
                          )}
                        </div>
                        {status === "pending" && !busy && (
                          <button
                            type="button"
                            onClick={() =>
                              setPendingFiles((prev) => prev.filter((f) => f !== file))
                            }
                            className="shrink-0 text-text-muted hover:text-destructive"
                            aria-label={`Remove ${file.name}`}
                          >
                            <X className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>

                <div className="flex items-center gap-2">
                  <Button onClick={() => handleUpload(pendingFiles)} disabled={busy}>
                    {busy && <Loader2 className="size-4 animate-spin" />}
                    Upload
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setPendingFiles([])}
                    disabled={busy}
                  >
                    Clear
                  </Button>
                </div>
              </div>
            )}
          </div>

          {/* Single-file status messages */}
          {!isBatch && uploadMutation.isPending && (
            <Alert variant="info">
              <Loader2 className="size-4 animate-spin" />
              <AlertDescription>Uploading...</AlertDescription>
            </Alert>
          )}

          {!isBatch && uploadMutation.isError && (
            <Alert variant="destructive">
              <AlertCircle className="size-4" />
              <AlertDescription>
                {uploadMutation.error?.message ?? "Upload failed"}
              </AlertDescription>
            </Alert>
          )}

          {!isBatch && uploadMutation.isSuccess && (
            <Alert variant="success">
              <Check className="size-4" />
              <AlertDescription>Upload successful! Redirecting...</AlertDescription>
            </Alert>
          )}

          {/* Multi-file progress */}
          {isBatch && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm text-text-secondary">
                <span>
                  {isUploading
                    ? `Uploading ${doneCount + 1} of ${totalCount}...`
                    : `${doneCount} of ${totalCount} complete`}
                </span>
                <span>
                  {Object.values(fileStatuses).filter((s) => s === "error").length > 0 &&
                    `${Object.values(fileStatuses).filter((s) => s === "error").length} failed`}
                </span>
              </div>
              {allDone && (
                <Button onClick={() => router.push(`/${workspace}/documents`)}>
                  <ArrowLeft className="size-3.5" />
                  View Documents
                </Button>
              )}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
