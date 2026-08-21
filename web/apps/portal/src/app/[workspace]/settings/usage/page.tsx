"use client";

import { Coins } from "lucide-react";

import { Card, CardHeader } from "@/components/ui/Card";
import { useUserTokenUsage } from "@/hooks/use-usage";
import { formatTokens } from "@/lib/utils";

export default function UsageSettingsPage() {
  const usage = useUserTokenUsage();
  const month = usage.data?.month;

  const pct =
    month?.limit == null ? null : month.limit === 0 ? 1 : Math.min(month.total / month.limit, 1);
  const barColor =
    pct === null
      ? ""
      : pct >= 1
        ? "bg-red-500"
        : pct >= 0.8
          ? "bg-amber-500"
          : "bg-emerald-500";

  return (
    <div className="max-w-2xl space-y-6">
      <Card>
        <CardHeader title="This Month" />
        {usage.isError ? (
          <p className="text-sm text-red-500">
            Failed to load usage
            {usage.error instanceof Error ? `: ${usage.error.message}` : "."}
          </p>
        ) : usage.isLoading ? (
          <p className="text-sm text-text-muted">Loading usage…</p>
        ) : !month ? (
          // Deploy skew: an older backend without the month block.
          <p className="text-sm text-text-muted">Usage data unavailable.</p>
        ) : (
          <div className="space-y-4">
            <div className="flex items-baseline justify-between">
              <span className="flex items-center gap-2 text-sm text-text-muted">
                <Coins className="size-4 text-amber-500" />
                {month.limit !== null
                  ? `${formatTokens(month.total)} of ${formatTokens(month.limit)} tokens`
                  : `${formatTokens(month.total)} tokens (no limit set)`}
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
                <div className="text-xs text-text-muted">Deep Research</div>
                <div className="font-mono text-text-primary">{formatTokens(month.chat)}</div>
              </div>
              <div className="rounded-lg border border-border-default px-3 py-2.5">
                <div className="text-xs text-text-muted">Document processing</div>
                <div className="font-mono text-text-primary">
                  {formatTokens(month.ingestion)}
                </div>
              </div>
            </div>
            <p className="text-xs text-text-muted">
              Usage resets on the 1st of each month (UTC). Deep Research and document processing both
              count toward your limit.
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}
