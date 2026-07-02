"use client";

import { useQuery } from "@tanstack/react-query";
import type { ArtifactResponse } from "@docu-store/types";
import { useArtifacts } from "./use-artifacts";
import { queryKeys } from "@/lib/query-keys";
import { authFetchJson } from "@/lib/auth-fetch";

export interface DashboardStats {
  totalArtifacts: number;
  totalPages: number;
  totalCompounds: number;
  withSummary: number;
}

export function useDashboardStats() {
  return useQuery({
    queryKey: queryKeys.dashboard.stats(),
    queryFn: async (): Promise<DashboardStats> => {
      const data = await authFetchJson<Record<string, number>>("/dashboard/stats");
      return {
        totalArtifacts: data.total_artifacts,
        totalPages: data.total_pages,
        totalCompounds: data.total_compounds,
        withSummary: data.with_summary,
      };
    },
  });
}

export function useDashboard() {
  const {
    data: stats,
    isLoading: statsLoading,
    error: statsError,
  } = useDashboardStats();

  const {
    data: artifactsData,
    isLoading: artifactsLoading,
    error: artifactsError,
  } = useArtifacts(0, 10);

  const recentArtifacts = (artifactsData ?? []) as ArtifactResponse[];

  return {
    stats: stats ?? {
      totalArtifacts: 0,
      totalPages: 0,
      totalCompounds: 0,
      withSummary: 0,
    },
    recentArtifacts,
    isLoading: statsLoading || artifactsLoading,
    error: statsError ?? artifactsError,
  };
}
