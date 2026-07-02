"use client";

import { Loader2, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import type { WorkflowMap } from "@docu-store/types";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { WorkflowStatusBadge } from "@/components/WorkflowStatusBadge";

interface WorkflowEntry {
  name: string;
  workflow_id: string;
  status: string;
  from_cache?: boolean;
}

/**
 * Parse a WorkflowMap into a flat array of workflow entries.
 */
export function parseWorkflows(
  data: unknown,
): WorkflowEntry[] | undefined {
  const map = (data as WorkflowMap | undefined)?.workflows;
  if (!map) return undefined;
  return Object.entries(map).map(([name, info]) => ({
    name,
    workflow_id: info.workflow_id,
    status: info.status,
    from_cache: info.from_cache,
  }));
}

interface WorkflowListProps {
  workflows: WorkflowEntry[] | undefined;
  rerunableWorkflows: Set<string>;
  onRerun: (name: string) => Promise<unknown>;
  isRerunning: boolean;
  rerunningName?: string;
  /** "cards" = grid of cards (artifact detail), "chips" = inline badges (page viewer) */
  variant?: "cards" | "chips";
}

export function WorkflowList({
  workflows,
  rerunableWorkflows,
  onRerun,
  isRerunning,
  rerunningName,
  variant = "cards",
}: WorkflowListProps) {
  if (!workflows || workflows.length === 0) {
    if (variant === "cards") {
      return (
        <p className="py-8 text-center text-sm text-text-muted">
          No workflows found.
        </p>
      );
    }
    return null;
  }

  const handleRerun = async (name: string) => {
    try {
      await onRerun(name);
    } catch {
      toast.error("Rerun failed", {
        description: `Could not rerun ${name.replace(/_/g, " ")}`,
      });
    }
  };

  const rerunButton = (w: WorkflowEntry) =>
    rerunableWorkflows.has(w.name) && w.status !== "RUNNING" ? (
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="rounded-full"
            onClick={() => handleRerun(w.name)}
            disabled={isRerunning}
            aria-label="Rerun"
          >
            {isRerunning && rerunningName === w.name ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RotateCcw className="size-4" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="top">Rerun</TooltipContent>
      </Tooltip>
    ) : null;

  if (variant === "chips") {
    return (
      <div className="flex flex-wrap gap-3">
        {workflows.map((w) => (
          <div
            key={w.name}
            className="flex items-center gap-2 rounded-lg border border-border-default bg-surface-elevated px-3 py-2"
          >
            <span className="text-xs font-medium text-text-primary">
              {w.name.replace(/_/g, " ")}
            </span>
            <WorkflowStatusBadge status={w.status} fromCache={w.from_cache} />
            {rerunButton(w)}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {workflows.map((w) => (
        <Card key={w.name}>
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-text-primary">
              {w.name.replace(/_/g, " ")}
            </span>
            <div className="flex items-center gap-2">
              <WorkflowStatusBadge status={w.status} fromCache={w.from_cache} />
              {rerunButton(w)}
            </div>
          </div>
          <p className="mt-2 truncate font-mono text-xs text-text-muted">
            {w.workflow_id}
          </p>
        </Card>
      ))}
    </div>
  );
}
