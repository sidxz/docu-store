"use client";

import { Tag } from "primereact/tag";

const STATUS_CONFIG: Record<string, { severity: "success" | "info" | "warning" | "danger" | "secondary"; icon: string }> = {
  RUNNING: { severity: "info", icon: "pi pi-spin pi-spinner" },
  COMPLETED: { severity: "success", icon: "pi pi-check" },
  FAILED: { severity: "danger", icon: "pi pi-times" },
  TIMED_OUT: { severity: "warning", icon: "pi pi-clock" },
  NOT_FOUND: { severity: "secondary", icon: "pi pi-minus" },
};

export function WorkflowStatusBadge({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.NOT_FOUND;

  return (
    <Tag
      value={status}
      severity={config.severity}
      icon={config.icon}
    />
  );
}
