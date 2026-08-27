"use client";

import { useQuery } from "@tanstack/react-query";

import { authFetchJson } from "@/lib/auth-fetch";
import { queryKeys } from "@/lib/query-keys";

export type ProcessingStage = "parsing" | "extracting" | "indexing" | "finishing" | "failed";

/** One row of GET /artifacts/processing — the caller's own in-flight documents. */
export interface ProcessingArtifact {
  artifact_id: string;
  source_filename: string | null;
  total: number;
  completed: number;
  running: number;
  failed: number;
  percent: number;
  stage: ProcessingStage;
  active: boolean;
  last_activity_at: string | null;
}

/** Polls fast while something is processing, slowly when idle. */
export function useProcessingArtifacts() {
  return useQuery({
    queryKey: queryKeys.artifacts.processing(),
    queryFn: () => authFetchJson<ProcessingArtifact[]>("/artifacts/processing"),
    refetchInterval: (query) => ((query.state.data?.length ?? 0) > 0 ? 6_000 : 30_000),
    refetchIntervalInBackground: false,
    retry: 1,
  });
}
