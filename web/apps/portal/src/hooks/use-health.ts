"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query-keys";
import { authFetchJson } from "@/lib/auth-fetch";

// ---------- Response types ----------

export interface GpuDevice {
  index: number;
  name: string;
  memory_total_mb: number;
  memory_used_mb: number;
  memory_free_mb: number;
}

export interface GpuInfo {
  cuda_available: boolean;
  mps_available: boolean;
  cuda_version: string | null;
  device_count: number;
  devices: GpuDevice[];
}

export interface SystemInfo {
  app_version: string;
  python_version: string;
  os_info: string;
  hostname: string;
  uptime_seconds: number;
  timestamp: string;
}

export interface ServiceStatus {
  name: string;
  status: "healthy" | "unhealthy" | "degraded" | "disabled";
  latency_ms: number | null;
  version: string | null;
  error: string | null;
  details: Record<string, unknown> | null;
}

export interface ModelStatus {
  name: string;
  loaded: boolean;
  device: string;
  model_name: string;
  inference_ok: boolean | null;
  error: string | null;
}

export interface ConfigSummary {
  app_env: string;
  llm_provider: string;
  llm_model: string;
  chat_llm_provider: string;
  chat_llm_model: string;
  embedding_model: string;
  embedding_device: string;
  smiles_model: string;
  smiles_device: string;
  reranker_enabled: boolean;
  reranker_model: string | null;
  reranker_device: string | null;
  kafka_enabled: boolean;
  temporal_address: string;
  temporal_max_concurrent_activities: number;
  temporal_max_concurrent_llm_activities: number;
  qdrant_url: string;
  blob_base_url: string;
}

export interface WorkerHeartbeat {
  worker_id: string;
  worker_type: string;
  worker_name: string;
  hostname: string;
  pid: number;
  status: "online" | "offline";
  gpu: GpuInfo;
  loaded_models: ModelStatus[];
  system: SystemInfo;
  started_at: string;
  last_heartbeat: string;
}

export interface DetailedHealthResponse {
  overall_status: "healthy" | "degraded" | "unhealthy";
  system: SystemInfo;
  gpu: GpuInfo;
  services: ServiceStatus[];
  models: ModelStatus[];
  config: ConfigSummary;
  workers: WorkerHeartbeat[];
  checked_at: string;
}

// ---------- Admin action types ----------

export type ReEmbedTarget = "text" | "smiles" | "summaries";

export const ALL_REEMBED_TARGETS: ReEmbedTarget[] = [
  "text",
  "smiles",
  "summaries",
];

export interface BulkWorkflowResponse {
  triggered: number;
  workflow_ids: string[];
  targets: ReEmbedTarget[];
}

// ---------- Hooks ----------

export function useDetailedHealth(refetchInterval: number | false = 30_000) {
  return useQuery({
    queryKey: queryKeys.health.detailed(),
    queryFn: () => authFetchJson<DetailedHealthResponse>("/system/health"),
    refetchInterval,
    retry: 1,
  });
}

export function useReembedAll() {
  return useMutation({
    mutationFn: (targets?: ReEmbedTarget[]) =>
      authFetchJson<BulkWorkflowResponse>("/system/reembed-all", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ targets: targets ?? ALL_REEMBED_TARGETS }),
      }),
  });
}
