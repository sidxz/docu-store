"use client";

import { useState } from "react";
import { CircleCheck, Download, Loader2, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { useAuthzHasRole } from "@duar-auth/react";

import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { authFetch, readErrorDetail } from "@/lib/auth-fetch";

const FALLBACK_FILENAME = "cser-training-export.zip";

/** Filename out of `attachment; filename="..."`, quoted or bare. */
function filenameFromDisposition(header: string | null): string {
  const match = header?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  return match?.[1] ?? FALLBACK_FILENAME;
}

/**
 * Number of files in a zip, read from its end-of-central-directory record: the
 * last 22 bytes when the archive carries no comment, which is what the server
 * writes. Returns null when that signature is not there, so the caller can skip
 * the check rather than guess from the size.
 */
async function zipEntryCount(blob: Blob): Promise<number | null> {
  if (blob.size < 22) return null;
  const tail = new DataView(await blob.slice(blob.size - 22).arrayBuffer());
  if (tail.getUint32(0, true) !== 0x06054b50) return null;
  return tail.getUint16(10, true);
}

export default function TrainingExportSettingsPage() {
  // Server gate is the `artifacts:hiledit` action, which editor and above hold.
  const canExport = useAuthzHasRole("editor");
  const [reviewedOnly, setReviewedOnly] = useState(true);
  const [since, setSince] = useState("");
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  if (!canExport) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Access Denied"
        description="Exporting training data needs the artifacts:hiledit action."
      />
    );
  }

  const download = async () => {
    setPending(true);
    setStatus(null);
    try {
      const params = new URLSearchParams({ only_reviewed: String(reviewedOnly) });
      if (since) params.set("since", since);
      const res = await authFetch(`/workspace/cser-training-export?${params}`);

      if (res.status === 403) {
        const text = "Your account does not have the artifacts:hiledit action in this workspace.";
        setStatus({ kind: "error", text });
        toast.error("Export refused", { description: text });
        return;
      }
      if (!res.ok) {
        const detail = await readErrorDetail(res);
        throw new Error(detail ?? res.statusText ?? `HTTP ${res.status}`);
      }

      const blob = await res.blob();
      if ((await zipEntryCount(blob)) === 1) {
        // manifest.json is the only entry, so no page made it into the bundle.
        const text = "The export holds no pages. Nothing matched these settings.";
        setStatus({ kind: "error", text });
        toast("Nothing to export", { description: text });
        return;
      }

      const filename = filenameFromDisposition(res.headers.get("Content-Disposition"));
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename;
      anchor.click();
      // Revoke after the click has handed the blob to the download, not before.
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      setStatus({ kind: "ok", text: `Downloaded ${filename}.` });
    } catch (e) {
      const text = e instanceof Error ? e.message : "Unknown error";
      setStatus({ kind: "error", text });
      toast.error("Export failed", { description: text });
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-6">
      <Card>
        <CardHeader title="CSER Training Export" />
        <p className="mb-5 text-xs text-text-muted">
          Downloads the chemical structure annotations in this workspace as a zip laid out as a
          structflo-cser data_dir: images/, ground_truth/, labels/ and manifest.json. Only pages you
          can view are included.
        </p>

        <div className="space-y-2">
          <Label className="text-xs text-text-muted">Contents</Label>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={reviewedOnly ? "reviewed" : "all"}
            onValueChange={(nv) => {
              if (nv) setReviewedOnly(nv === "reviewed");
            }}
          >
            <ToggleGroupItem value="reviewed">Reviewed pages only</ToggleGroupItem>
            <ToggleGroupItem value="all">Include machine output</ToggleGroupItem>
          </ToggleGroup>
          <p className="text-xs text-text-muted">
            Machine output has not been checked by a person. Include it to bootstrap a first
            training run.
          </p>
        </div>

        <div className="mt-5 space-y-2">
          <Label htmlFor="since" className="text-xs text-text-muted">
            Corrected since
          </Label>
          <Input
            id="since"
            type="date"
            value={since}
            onChange={(e) => setSince(e.target.value)}
            className="h-8 w-44"
          />
          <p className="text-xs text-text-muted">
            Optional. Keeps only pages corrected on or after this date. Empty exports everything.
          </p>
        </div>

        <div className="mt-5 flex items-center gap-3">
          <Button onClick={download} disabled={pending} size="sm">
            {pending ? <Loader2 className="animate-spin" /> : <Download />}
            {pending ? "Building export…" : "Download export"}
          </Button>
          {pending && (
            <span className="text-xs text-text-muted">
              The zip is built server side and can take a while on a large workspace.
            </span>
          )}
        </div>

        {status && !pending && (
          <p
            className={`mt-3 flex items-center gap-1.5 text-xs ${
              status.kind === "ok" ? "text-text-muted" : "text-red-500"
            }`}
          >
            {status.kind === "ok" && <CircleCheck className="size-3.5 text-emerald-500" />}
            {status.text}
          </p>
        )}
      </Card>
    </div>
  );
}
