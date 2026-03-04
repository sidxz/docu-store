"use client";

import { Loader2, CheckCircle2, XCircle, Clock, MinusCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";

const STATUS_CONFIG: Record<
  string,
  { icon: LucideIcon; color: string; bg: string; spin?: boolean }
> = {
  RUNNING: {
    icon: Loader2,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-50 dark:bg-blue-500/10",
    spin: true,
  },
  COMPLETED: {
    icon: CheckCircle2,
    color: "text-emerald-600 dark:text-emerald-400",
    bg: "bg-emerald-50 dark:bg-emerald-500/10",
  },
  FAILED: {
    icon: XCircle,
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-50 dark:bg-red-500/10",
  },
  TIMED_OUT: {
    icon: Clock,
    color: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-50 dark:bg-amber-500/10",
  },
  NOT_FOUND: {
    icon: MinusCircle,
    color: "text-text-muted",
    bg: "bg-border-subtle",
  },
};

export function WorkflowStatusBadge({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.NOT_FOUND;
  const Icon = config.icon;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${config.bg} ${config.color}`}
    >
      <Icon className={`h-3.5 w-3.5 ${config.spin ? "animate-spin" : ""}`} />
      {status}
    </span>
  );
}
