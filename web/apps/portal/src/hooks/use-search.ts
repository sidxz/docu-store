"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { apiClient } from "@docu-store/api-client";
import { throwApiError } from "@/lib/api-error";
import { queryKeys } from "@/lib/query-keys";
import { useAnalytics } from "@/hooks/use-analytics";

export interface SearchParams {
  query_text: string;
  tags?: string[];
  entity_types?: string[];
  tag_match_mode?: "any" | "all";
}

// ── Query-based hooks (URL-driven, cacheable, back-button friendly) ─────────

export function useTextSearchQuery(params: SearchParams | null) {
  const { trackEvent } = useAnalytics();
  return useQuery({
    queryKey: queryKeys.search.text(params?.query_text ?? "", params?.tags, params?.tag_match_mode),
    queryFn: async () => {
      const t0 = performance.now();
      const { data, error, response } = await apiClient.POST("/search/pages", {
        body: {
          query_text: params!.query_text,
          limit: 10,
          tags: params!.tags,
          entity_types: params!.entity_types,
          tag_match_mode: params!.tag_match_mode,
        },
      });
      if (error) throwApiError("Failed to search pages", error, response.status);
      const latencyMs = Math.round(performance.now() - t0);
      const resultCount = (data as { results?: unknown[] })?.results?.length ?? 0;
      trackEvent("search_executed", {
        search_type: "pages",
        query_length: params!.query_text.length,
        result_count: resultCount,
        zero_results: resultCount === 0 ? 1 : 0,
      });
      trackEvent("search_client_latency", { search_type: "pages", latency_ms: latencyMs });
      return data;
    },
    enabled: !!params?.query_text,
    staleTime: 5 * 60 * 1000, // 5 min — back navigation serves from cache
  });
}

export function useSummarySearchQuery(params: SearchParams | null) {
  const { trackEvent } = useAnalytics();
  return useQuery({
    queryKey: queryKeys.search.summary(params?.query_text ?? "", params?.tags, params?.tag_match_mode),
    queryFn: async () => {
      const t0 = performance.now();
      const { data, error, response } = await apiClient.POST("/search/summaries", {
        body: {
          query_text: params!.query_text,
          limit: 10,
          tags: params!.tags,
          entity_types_filter: params!.entity_types,
          tag_match_mode: params!.tag_match_mode,
        },
      });
      if (error) throwApiError("Failed to search summaries", error, response.status);
      const latencyMs = Math.round(performance.now() - t0);
      const resultCount = (data as { results?: unknown[] })?.results?.length ?? 0;
      trackEvent("search_executed", {
        search_type: "summaries",
        query_length: params!.query_text.length,
        result_count: resultCount,
        zero_results: resultCount === 0 ? 1 : 0,
      });
      trackEvent("search_client_latency", { search_type: "summaries", latency_ms: latencyMs });
      return data;
    },
    enabled: !!params?.query_text,
    staleTime: 5 * 60 * 1000,
  });
}

export function useHierarchicalSearchQuery(params: (SearchParams & { include_chunks?: boolean }) | null) {
  const { trackEvent } = useAnalytics();
  return useQuery({
    queryKey: queryKeys.search.hierarchical(params?.query_text ?? "", params?.tags, params?.tag_match_mode, params?.include_chunks),
    queryFn: async () => {
      const t0 = performance.now();
      const { data, error, response } = await apiClient.POST("/search/hierarchical", {
        body: {
          query_text: params!.query_text,
          limit: 10,
          include_chunks: params!.include_chunks ?? true,
          tags: params!.tags,
          entity_types_filter: params!.entity_types,
          tag_match_mode: params!.tag_match_mode,
        },
      });
      if (error) throwApiError("Failed to perform hierarchical search", error, response.status);
      const latencyMs = Math.round(performance.now() - t0);
      const hData = data as { summary_hits?: unknown[]; chunk_hits?: unknown[] };
      const resultCount = (hData?.summary_hits?.length ?? 0) + (hData?.chunk_hits?.length ?? 0);
      trackEvent("search_executed", {
        search_type: "hierarchical",
        query_length: params!.query_text.length,
        result_count: resultCount,
        zero_results: resultCount === 0 ? 1 : 0,
      });
      trackEvent("search_client_latency", { search_type: "hierarchical", latency_ms: latencyMs });
      return data;
    },
    enabled: !!params?.query_text,
    staleTime: 5 * 60 * 1000,
  });
}

// ── Mutation-based hooks (for SearchCommand inline preview & compounds) ──────

export function useHierarchicalSearchMutation() {
  return useMutation({
    mutationFn: async (params: {
      query_text: string;
      limit?: number;
      include_chunks?: boolean;
    }) => {
      const { data, error, response } = await apiClient.POST("/search/hierarchical", {
        body: {
          query_text: params.query_text,
          limit: params.limit ?? 6,
          include_chunks: params.include_chunks ?? true,
        },
      });
      if (error) throwApiError("Failed to perform hierarchical search", error, response.status);
      return data;
    },
  });
}

export function useSearchCompounds() {
  const { trackEvent } = useAnalytics();
  return useMutation({
    mutationFn: async (params: {
      query_smiles: string;
      limit?: number;
      artifact_id?: string;
      score_threshold?: number;
    }) => {
      const { data, error, response } = await apiClient.POST("/search/compounds", {
        body: {
          query_smiles: params.query_smiles,
          limit: params.limit ?? 10,
          artifact_id: params.artifact_id,
          score_threshold: params.score_threshold,
        },
      });
      if (error) throwApiError("Failed to search compounds", error, response.status);
      const resultCount = (data as { results?: unknown[] })?.results?.length ?? 0;
      trackEvent("compound_searched", { result_count: resultCount });
      return data;
    },
  });
}
