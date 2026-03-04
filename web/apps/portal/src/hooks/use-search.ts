"use client";

import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@docu-store/api-client";

// All search operations use useMutation instead of useQuery because:
// - Search is triggered by explicit user action (button click), not on mount
// - The same query text may return different results over time as the index grows
// - useMutation gives us isPending / isSuccess / reset without stale-time caching

export function useSearchPages() {
  return useMutation({
    mutationFn: async (params: {
      query_text: string;
      limit?: number;
      artifact_id?: string;
      score_threshold?: number;
    }) => {
      const { data, error } = await apiClient.POST("/search/pages", {
        body: {
          query_text: params.query_text,
          limit: params.limit ?? 10,
          artifact_id: params.artifact_id,
          score_threshold: params.score_threshold,
        },
      });
      if (error) throw new Error("Failed to search pages");
      return data;
    },
  });
}

export function useSearchSummaries() {
  return useMutation({
    mutationFn: async (params: {
      query_text: string;
      limit?: number;
      entity_type?: "page" | "artifact";
      artifact_id?: string;
      score_threshold?: number;
    }) => {
      const { data, error } = await apiClient.POST("/search/summaries", {
        body: {
          query_text: params.query_text,
          limit: params.limit ?? 10,
          entity_type: params.entity_type,
          artifact_id: params.artifact_id,
          score_threshold: params.score_threshold,
        },
      });
      if (error) throw new Error("Failed to search summaries");
      return data;
    },
  });
}

export function useHierarchicalSearch() {
  return useMutation({
    mutationFn: async (params: {
      query_text: string;
      limit?: number;
      score_threshold?: number;
      include_chunks?: boolean;
    }) => {
      const { data, error } = await apiClient.POST("/search/hierarchical", {
        body: {
          query_text: params.query_text,
          limit: params.limit ?? 10,
          score_threshold: params.score_threshold,
          include_chunks: params.include_chunks ?? true,
        },
      });
      if (error) throw new Error("Failed to perform hierarchical search");
      return data;
    },
  });
}

export function useSearchCompounds() {
  return useMutation({
    mutationFn: async (params: {
      query_smiles: string;
      limit?: number;
      artifact_id?: string;
      score_threshold?: number;
    }) => {
      const { data, error } = await apiClient.POST("/search/compounds", {
        body: {
          query_smiles: params.query_smiles,
          limit: params.limit ?? 10,
          artifact_id: params.artifact_id,
          score_threshold: params.score_threshold,
        },
      });
      if (error) throw new Error("Failed to search compounds");
      return data;
    },
  });
}
