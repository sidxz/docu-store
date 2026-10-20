"use client";

import { AlertTriangle, HardDrive, ShieldAlert } from "lucide-react";
import { useAuthzHasRole } from "@duar-auth/react";

import { LimitInput } from "@/components/settings/LimitInput";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { useSetStorageLimit, useWorkspaceStorage } from "@/hooks/use-workspace-storage";
import { formatFileSize } from "@/lib/utils";

const MIB = 1024 * 1024;

export default function StorageSettingsPage() {
  const isAdmin = useAuthzHasRole("admin");
  const storage = useWorkspaceStorage();
  const setLimit = useSetStorageLimit();

  if (!isAdmin) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Access Denied"
        description="You need admin privileges to manage storage."
      />
    );
  }

  if (storage.isError) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Failed to load storage"
        description={
          storage.error instanceof Error ? storage.error.message : "An unknown error occurred."
        }
      />
    );
  }

  const data = storage.data;
  const effective = data?.effective_limit_bytes ?? null;
  const uploaded = data?.uploaded_bytes ?? 0;
  const pct = effective === null ? null : effective === 0 ? 1 : Math.min(uploaded / effective, 1);
  const barColor =
    pct === null
      ? ""
      : pct >= 1
        ? "bg-red-500"
        : pct >= 0.8
          ? "bg-amber-500"
          : "bg-emerald-500";
  const cap = data?.cap_bytes ?? null;

  return (
    <div className="max-w-2xl space-y-6">
      <Card>
        <CardHeader title="Storage" />
        {storage.isLoading || !data ? (
          <p className="text-sm text-text-muted">Loading storage…</p>
        ) : (
          <div className="space-y-4">
            <div className="flex items-baseline justify-between">
              <span className="flex items-center gap-2 text-sm text-text-muted">
                <HardDrive className="size-4 text-text-muted" />
                {effective !== null
                  ? `${formatFileSize(uploaded)} of ${formatFileSize(effective)} uploaded`
                  : `${formatFileSize(uploaded)} uploaded (no limit set)`}
              </span>
              {pct !== null && (
                <span className="font-mono text-xs text-text-muted">
                  {Math.round(pct * 100)}%
                </span>
              )}
            </div>
            {pct !== null && (
              <div className="h-2 w-full overflow-hidden rounded-full bg-surface-sunken">
                <div
                  className={`h-full rounded-full ${barColor}`}
                  style={{ width: `${pct * 100}%` }}
                />
              </div>
            )}
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="rounded-lg border border-border-default px-3 py-2.5">
                <div className="text-xs text-text-muted">Uploaded files</div>
                <div className="font-mono text-text-primary">{formatFileSize(uploaded)}</div>
              </div>
              <div className="rounded-lg border border-border-default px-3 py-2.5">
                <div className="text-xs text-text-muted">On disk</div>
                <div className="font-mono text-text-primary">
                  {data.on_disk_bytes === null ? "unavailable" : formatFileSize(data.on_disk_bytes)}
                </div>
              </div>
            </div>
            <p className="text-xs text-text-muted">
              The limit counts uploaded files. On disk also includes the page images and other
              files DocuStore generates, and refreshes every few minutes.
            </p>
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="Limit" />
        <p className="mb-3 text-xs text-text-muted">
          Uploads that would go over the limit are refused; existing documents keep working.
          Empty = no workspace limit. Applies to admins too.
        </p>
        <div className="flex items-center gap-4 text-sm">
          <span className="font-mono text-text-primary">
            {data?.limit_bytes == null ? "No limit" : formatFileSize(data.limit_bytes)}
          </span>
          <LimitInput
            onSave={(mb) => setLimit.mutate(mb === null ? null : mb * MIB)}
            isPending={setLimit.isPending}
            placeholder="MB, e.g. 500"
            max={cap === null ? undefined : Math.floor(cap / MIB)}
          />
        </div>
        {cap !== null && (
          <p className="mt-2 text-xs text-text-muted">
            This deployment caps every workspace at {formatFileSize(cap)}.
          </p>
        )}
        {setLimit.isError && (
          <p className="mt-2 text-xs text-red-500">{setLimit.error.message}</p>
        )}
      </Card>
    </div>
  );
}
