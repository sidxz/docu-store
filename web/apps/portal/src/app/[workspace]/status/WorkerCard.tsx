"use client";

import { useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Cpu,
  HardDrive,
  XCircle,
} from "lucide-react";

import type { WorkerHeartbeat } from "@/hooks/use-health";
import { fmtUptime, statusColor, statusDot, timeAgo } from "./status-helpers";

const TYPE_LABELS: Record<string, string> = {
  api_server: "API",
  temporal_cpu: "CPU/IO",
  temporal_llm: "LLM",
  pipeline: "Pipeline",
  read_projector: "Projector",
  plugin_consumer: "Plugin",
};

function WorkerTypeBadge({ type }: { type: string }) {
  return (
    <span className="rounded bg-surface-sunken px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
      {TYPE_LABELS[type] ?? type}
    </span>
  );
}

function DeviceBadge({ device }: { device: string }) {
  const cls =
    device === "cuda"
      ? "bg-green-500/10 text-green-600 dark:text-green-400"
      : device === "mps"
        ? "bg-blue-500/10 text-blue-600 dark:text-blue-400"
        : "bg-surface-sunken text-text-muted";
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>
      {device}
    </span>
  );
}

export function WorkerCard({ worker }: { worker: WorkerHeartbeat }) {
  const [expanded, setExpanded] = useState(false);
  const offline = worker.status === "offline";
  const hasGpuDevices = worker.gpu.devices.length > 0;
  const hasModels = worker.loaded_models.length > 0;
  const hasDetails = hasGpuDevices || hasModels;

  const uptimeSeconds =
    (Date.now() - new Date(worker.started_at).getTime()) / 1000;

  return (
    <div
      className={`rounded-xl border bg-surface-elevated transition-opacity ${
        offline
          ? "border-red-500/20 opacity-60"
          : "border-border-default"
      }`}
    >
      {/* Header */}
      <button
        type="button"
        className="flex w-full items-center gap-2 px-4 py-3 text-left"
        onClick={() => hasDetails && setExpanded(!expanded)}
        disabled={!hasDetails}
      >
        <span
          className={`h-2.5 w-2.5 shrink-0 rounded-full ${statusDot(worker.status)}`}
        />
        <span className="flex-1 text-sm font-medium text-text-primary">
          {worker.worker_name}
        </span>
        <WorkerTypeBadge type={worker.worker_type} />
        <span className={`text-xs font-medium ${statusColor(worker.status)}`}>
          {offline ? "Offline" : "Online"}
        </span>
        {hasDetails ? (
          expanded ? (
            <ChevronDown className="h-4 w-4 text-text-muted" />
          ) : (
            <ChevronRight className="h-4 w-4 text-text-muted" />
          )
        ) : (
          <span className="w-4" />
        )}
      </button>

      {/* Info row — always visible */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 border-t border-border-default px-4 py-2 text-xs text-text-muted sm:grid-cols-4">
        <div className="flex items-center gap-1">
          <HardDrive className="h-3 w-3" />
          <span className="truncate">{worker.hostname}</span>
        </div>
        <div className="flex items-center gap-1">
          <Cpu className="h-3 w-3" />
          <span>PID {worker.pid}</span>
        </div>
        <div>
          Uptime: {fmtUptime(uptimeSeconds)}
        </div>
        <div>
          Heartbeat: {timeAgo(worker.last_heartbeat)}
        </div>
      </div>

      {/* GPU summary — always visible if CUDA/MPS */}
      {(worker.gpu.cuda_available || worker.gpu.mps_available) && (
        <div className="flex items-center gap-2 border-t border-border-default px-4 py-2">
          {worker.gpu.cuda_available && (
            <span className="rounded bg-green-500/10 px-1.5 py-0.5 text-[10px] font-medium text-green-600 dark:text-green-400">
              CUDA {worker.gpu.cuda_version ?? ""}
            </span>
          )}
          {worker.gpu.mps_available && (
            <span className="rounded bg-blue-500/10 px-1.5 py-0.5 text-[10px] font-medium text-blue-600 dark:text-blue-400">
              MPS
            </span>
          )}
          <span className="text-xs text-text-muted">
            {worker.gpu.device_count} GPU{worker.gpu.device_count !== 1 ? "s" : ""}
          </span>
        </div>
      )}

      {/* Expandable detail section */}
      {expanded && hasDetails && (
        <div className="border-t border-border-default bg-surface-sunken/30 px-4 py-3 space-y-3">
          {/* GPU devices */}
          {hasGpuDevices && (
            <div className="space-y-2">
              {worker.gpu.devices.map((device) => {
                const pct = Math.round(
                  (device.memory_used_mb / device.memory_total_mb) * 100,
                );
                return (
                  <div key={device.index}>
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-text-primary">
                        GPU {device.index}: {device.name}
                      </span>
                      <span className="text-text-muted">
                        {device.memory_used_mb} / {device.memory_total_mb} MB (
                        {pct}%)
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 w-full rounded-full bg-surface-sunken">
                      <div
                        className={`h-1.5 rounded-full transition-all ${
                          pct > 90
                            ? "bg-red-500"
                            : pct > 70
                              ? "bg-amber-500"
                              : "bg-emerald-500"
                        }`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Loaded models */}
          {hasModels && (
            <div className="space-y-1">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                Models
              </p>
              {worker.loaded_models.map((model) => (
                <div
                  key={model.name}
                  className="flex items-center gap-2 text-xs"
                >
                  {model.inference_ok === true ? (
                    <Check className="h-3 w-3 shrink-0 text-ds-success" />
                  ) : model.inference_ok === false ? (
                    <XCircle className="h-3 w-3 shrink-0 text-ds-error" />
                  ) : (
                    <span className="h-3 w-3 shrink-0 rounded-full bg-gray-400/40" />
                  )}
                  <span className="flex-1 text-text-primary">{model.name}</span>
                  <DeviceBadge device={model.device} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
