"use client";

import { CheckCircle2, Clock, History, Loader2, MinusCircle, XCircle, type LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { severityToVariant, type PrimeSeverity } from "@/lib/severity";

const STATUS_CONFIG: Record<
  string,
  { severity: PrimeSeverity; icon: LucideIcon; spin?: boolean }
> = {
  RUNNING: { severity: "info", icon: Loader2, spin: true },
  COMPLETED: { severity: "success", icon: CheckCircle2 },
  FAILED: { severity: "danger", icon: XCircle },
  TIMED_OUT: { severity: "warning", icon: Clock },
  NOT_FOUND: { severity: "secondary", icon: MinusCircle },
};

export function WorkflowStatusBadge({ status, fromCache }: { status: string; fromCache?: boolean }) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.NOT_FOUND;
  const Icon = config.icon;

  return (
    <span className="inline-flex items-center gap-1">
      <Badge variant={severityToVariant[config.severity]}>
        <Icon className={config.spin ? "size-3 animate-spin" : "size-3"} />
        {status}
      </Badge>
      {fromCache && (
        <span title="Cached — workflow history expired in Temporal">
          <History className="size-3 text-text-muted" />
        </span>
      )}
    </span>
  );
}
