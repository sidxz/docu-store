"use client";

import { useMemo } from "react";
import { useArtifacts } from "./use-artifacts";
import type { ArtifactResponse } from "@docu-store/types";

interface DashboardStats {
  totalArtifacts: number;
  totalPages: number;
  totalCompounds: number;
  withSummary: number;
}

export function useDashboard() {
  // Fetches up to 100 artifacts in one call and aggregates KPIs client-side.
  // A dedicated /dashboard/stats endpoint could replace this in the future.
  const { data, isLoading, error } = useArtifacts(0, 100);

  const stats = useMemo<DashboardStats>(() => {
    const artifacts = (data as ArtifactResponse[] | undefined) ?? [];
    let totalPages = 0;
    let totalCompounds = 0;
    let withSummary = 0;

    for (const a of artifacts) {
      if (Array.isArray(a.pages)) {
        totalPages += a.pages.length;
        for (const p of a.pages) {
          if (typeof p === "object" && p !== null) {
            totalCompounds += p.compound_mentions?.length ?? 0;
          }
        }
      }
      if (a.summary_candidate?.summary) {
        withSummary++;
      }
    }

    return {
      totalArtifacts: artifacts.length,
      totalPages,
      totalCompounds,
      withSummary,
    };
  }, [data]);

  const recentArtifacts = useMemo(() => {
    const artifacts = (data as ArtifactResponse[] | undefined) ?? [];
    return artifacts.slice(0, 8);
  }, [data]);

  return { stats, recentArtifacts, isLoading, error };
}
