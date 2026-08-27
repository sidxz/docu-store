"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { CircleAlert, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Progress } from "@/components/ui/progress";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { type ProcessingArtifact, useProcessingArtifacts } from "@/hooks/use-processing-artifacts";

const STAGE_LABEL: Record<ProcessingArtifact["stage"], string> = {
  parsing: "Reading pages",
  extracting: "Extracting content",
  indexing: "Indexing",
  finishing: "Finishing up",
  failed: "Needs attention",
};

function Row({ item, workspace }: { item: ProcessingArtifact; workspace: string }) {
  const failed = item.failed > 0;
  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <div className="flex items-baseline justify-between gap-3">
        <Link
          href={`/${workspace}/documents/${item.artifact_id}`}
          className="min-w-0 truncate text-sm font-medium text-text-primary hover:underline"
        >
          {item.source_filename ?? "Untitled document"}
        </Link>
        <span className="shrink-0 font-mono text-xs tabular-nums text-text-muted">
          {item.percent}%
        </span>
      </div>
      <Progress
        value={item.active && item.total === 0 ? null : item.percent}
        className={`mt-2 h-1.5 ${failed ? "[&>div]:bg-red-500" : ""}`}
      />
      <p className={`mt-1.5 text-xs ${failed ? "text-red-500" : "text-text-muted"}`}>
        {failed
          ? `${item.failed} step${item.failed === 1 ? "" : "s"} failed · open to retry`
          : `${STAGE_LABEL[item.stage]} · ${item.completed} of ${item.total} steps`}
      </p>
    </li>
  );
}

/**
 * Topbar badge for the caller's documents still moving through the pipeline.
 * Renders nothing when there is nothing in flight.
 */
export function ProcessingIndicator() {
  const { workspace } = useParams<{ workspace: string }>();
  const { data } = useProcessingArtifacts();
  const items = data ?? [];
  if (items.length === 0) return null;

  const running = items.filter((i) => i.active).length;
  const onlyFailures = running === 0;
  const label = onlyFailures
    ? `${items.length} document${items.length === 1 ? "" : "s"} need attention`
    : `Processing ${running} document${running === 1 ? "" : "s"}`;

  return (
    <Popover>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="sm" className="gap-1.5" aria-label={label}>
              {onlyFailures ? (
                <CircleAlert className="size-4 text-red-500" />
              ) : (
                <Loader2 className="size-4 animate-spin text-primary" />
              )}
              <span className="font-mono text-xs tabular-nums">{items.length}</span>
            </Button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent side="bottom">{label}</TooltipContent>
      </Tooltip>
      <PopoverContent align="end" className="w-80 p-4">
        <p className="mb-3 text-sm font-semibold text-text-primary">{label}</p>
        <ul className="divide-y divide-border-default">
          {items.map((item) => (
            <Row key={item.artifact_id} item={item} workspace={workspace} />
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
