"use client";

import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query-keys";
import { authFetchJson } from "@/lib/auth-fetch";

// ---------- Response types ----------

interface WorkflowTypeStats {
  workflow_type: string;
  count: number;
  avg_duration_seconds: number;
  min_duration_seconds: number;
  max_duration_seconds: number;
  p95_duration_seconds: number;
}

interface ActiveWorkflow {
  workflow_type: string;
  count: number;
}

interface FailedWorkflow {
  workflow_id: string;
  workflow_type: string;
  started_at: string | null;
  closed_at: string | null;
  failure_message: string | null;
}

interface WorkflowStatsResponse {
  completed: WorkflowTypeStats[];
  active: ActiveWorkflow[];
  recent_failures: FailedWorkflow[];
}

interface PipelineStatsResponse {
  total_artifacts: number;
  total_pages: number;
  pages_with_text: number;
  pages_with_summary: number;
  pages_with_compounds: number;
  pages_with_tags: number;
}

interface CollectionStats {
  collection_name: string;
  points_count: number;
  indexed_vectors_count: number;
  status: string;
}

interface VectorStatsResponse {
  collections: CollectionStats[];
  embedding_model: Record<string, string | number>;
  reranker: Record<string, string | number> | null;
}

// ---------- Hooks ----------

export function useWorkflowStats() {
  return useQuery({
    queryKey: queryKeys.stats.workflows(),
    queryFn: () => authFetchJson<WorkflowStatsResponse>("/stats/workflows"),
    refetchInterval: 30_000,
  });
}

export function usePipelineStats() {
  return useQuery({
    queryKey: queryKeys.stats.pipeline(),
    queryFn: () => authFetchJson<PipelineStatsResponse>("/stats/pipeline"),
    refetchInterval: 30_000,
  });
}

export function useVectorStats() {
  return useQuery({
    queryKey: queryKeys.stats.vectors(),
    queryFn: () => authFetchJson<VectorStatsResponse>("/stats/vectors"),
    refetchInterval: 60_000,
  });
}

// ---------- Analytics aggregation types ----------

interface TokenUsageBucket {
  date: string;
  mode: string;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  message_count: number;
}

interface TokenUsageStatsResponse {
  buckets: TokenUsageBucket[];
  total_tokens: number;
  total_messages: number;
}

interface StepLatencyStats {
  step_name: string;
  count: number;
  avg_ms: number;
  p50_ms: number;
  p95_ms: number;
  max_ms: number;
}

interface ChatLatencyStatsResponse {
  steps: StepLatencyStats[];
  overall_avg_ms: number;
  overall_p95_ms: number;
}

interface SearchQualityStats {
  search_mode: string;
  total_searches: number;
  zero_result_count: number;
  zero_result_rate: number;
  avg_result_count: number;
}

interface SearchQualityStatsResponse {
  modes: SearchQualityStats[];
  total_searches: number;
  overall_zero_result_rate: number;
}

interface GroundingBucket {
  mode: string;
  total_messages: number;
  grounded_count: number;
  not_grounded_count: number;
  grounded_rate: number;
  avg_confidence: number;
}

interface GroundingStatsResponse {
  modes: GroundingBucket[];
  overall_grounded_rate: number;
  overall_avg_confidence: number;
}

// ---------- Analytics aggregation hooks ----------

export function useTokenUsageStats(period = "week") {
  return useQuery({
    queryKey: queryKeys.stats.tokenUsage(period),
    queryFn: () =>
      authFetchJson<TokenUsageStatsResponse>(`/stats/token-usage?period=${period}`),
    refetchInterval: 60_000,
  });
}

export function useChatLatencyStats(period = "week") {
  return useQuery({
    queryKey: queryKeys.stats.chatLatency(period),
    queryFn: () =>
      authFetchJson<ChatLatencyStatsResponse>(`/stats/chat-latency?period=${period}`),
    refetchInterval: 60_000,
  });
}

export function useSearchQualityStats(period = "week") {
  return useQuery({
    queryKey: queryKeys.stats.searchQuality(period),
    queryFn: () =>
      authFetchJson<SearchQualityStatsResponse>(`/stats/search-quality?period=${period}`),
    refetchInterval: 60_000,
  });
}

export function useGroundingStats(period = "week") {
  return useQuery({
    queryKey: queryKeys.stats.grounding(period),
    queryFn: () =>
      authFetchJson<GroundingStatsResponse>(`/stats/grounding?period=${period}`),
    refetchInterval: 60_000,
  });
}

// ---------- Knowledge gaps & citation frequency types ----------

interface KnowledgeGapEntry {
  entity_text: string;
  entity_type: string;
  query_count: number;
  gap_count: number;
  gap_rate: number;
}

interface KnowledgeGapsResponse {
  gaps: KnowledgeGapEntry[];
  total_unique_entities: number;
  total_gap_entities: number;
}

interface CitedArtifactEntry {
  artifact_id: string;
  artifact_title: string | null;
  citation_count: number;
  unique_conversation_count: number;
}

interface UncitedArtifactEntry {
  artifact_id: string;
  artifact_title: string | null;
}

interface CitationFrequencyResponse {
  most_cited: CitedArtifactEntry[];
  least_cited: CitedArtifactEntry[];
  never_cited: UncitedArtifactEntry[];
  never_cited_count: number;
  total_artifacts: number;
}

// ---------- Knowledge gaps & citation frequency hooks ----------

export function useKnowledgeGaps(period = "week") {
  return useQuery({
    queryKey: queryKeys.stats.knowledgeGaps(period),
    queryFn: () =>
      authFetchJson<KnowledgeGapsResponse>(`/stats/knowledge-gaps?period=${period}`),
    refetchInterval: 60_000,
  });
}

export function useCitationFrequency(period = "week") {
  return useQuery({
    queryKey: queryKeys.stats.citationFrequency(period),
    queryFn: () =>
      authFetchJson<CitationFrequencyResponse>(`/stats/citation-frequency?period=${period}`),
    refetchInterval: 60_000,
  });
}

// ---------- Re-exports for page consumption ----------

export type {
  WorkflowTypeStats,
  ActiveWorkflow,
  FailedWorkflow,
  WorkflowStatsResponse,
  PipelineStatsResponse,
  CollectionStats,
  VectorStatsResponse,
  TokenUsageBucket,
  TokenUsageStatsResponse,
  StepLatencyStats,
  ChatLatencyStatsResponse,
  SearchQualityStats,
  SearchQualityStatsResponse,
  GroundingBucket,
  GroundingStatsResponse,
  KnowledgeGapEntry,
  KnowledgeGapsResponse,
  CitedArtifactEntry,
  UncitedArtifactEntry,
  CitationFrequencyResponse,
};
