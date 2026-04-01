"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import type { WorkerHeartbeat } from "@/hooks/use-health";
import { WorkerCard } from "./WorkerCard";

export function WorkersSection({ workers }: { workers: WorkerHeartbeat[] }) {
  const online = workers.filter((w) => w.status === "online").length;

  // Sort: online first, then by worker_type for consistency
  const sorted = [...workers].sort((a, b) => {
    if (a.status !== b.status) return a.status === "online" ? -1 : 1;
    return a.worker_type.localeCompare(b.worker_type);
  });

  return (
    <Card>
      <CardHeader
        title="Workers"
        action={
          workers.length > 0 ? (
            <span className="rounded-full bg-surface-sunken px-2 py-0.5 text-xs font-medium text-text-muted">
              {online}/{workers.length} online
            </span>
          ) : undefined
        }
      />
      {sorted.length === 0 ? (
        <p className="py-6 text-center text-sm text-text-muted">
          No worker heartbeats received yet.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {sorted.map((worker) => (
            <WorkerCard key={worker.worker_id} worker={worker} />
          ))}
        </div>
      )}
    </Card>
  );
}
