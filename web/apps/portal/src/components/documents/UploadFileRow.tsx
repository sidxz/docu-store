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
