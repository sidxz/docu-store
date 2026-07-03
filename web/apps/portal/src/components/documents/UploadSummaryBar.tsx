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
