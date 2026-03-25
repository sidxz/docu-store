import type { WorkflowMap } from "@docu-store/types";

/**
 * Polls every 3s while any workflow is RUNNING; stops once all settle.
 * Shared between useArtifactWorkflows and usePageWorkflows.
 */
export function workflowPollingInterval(query: { state: { data: unknown } }): number | false {
  const workflows = (query.state.data as WorkflowMap | undefined)?.workflows;
  const hasRunning = workflows
    ? Object.values(workflows).some((w) => w.status === "RUNNING")
    : false;
  return hasRunning ? 3000 : false;
}

/**
 * Centralized TanStack Query key factory.
 *
 * Using a factory (functions that return arrays) rather than bare string arrays
 * makes it easy to invalidate whole subtrees:
 *   - invalidate all artifact data:       queryKeys.artifacts.all
 *   - invalidate one artifact + children: queryKeys.artifacts.detail(id)
 *   - invalidate just workflows for one:  queryKeys.artifacts.workflows(id)
 */
export const queryKeys = {
  artifacts: {
    all: ["artifacts"] as const,
    list: () => [...queryKeys.artifacts.all, "list"] as const,
    detail: (id: string) => [...queryKeys.artifacts.all, id] as const,
    workflows: (id: string) =>
      [...queryKeys.artifacts.all, id, "workflows"] as const,
    summary: (id: string) =>
      [...queryKeys.artifacts.all, id, "summary"] as const,
    permissions: (id: string) =>
      [...queryKeys.artifacts.all, id, "permissions"] as const,
  },
  pages: {
    all: ["pages"] as const,
    list: (artifactId: string) =>
      [...queryKeys.pages.all, "list", artifactId] as const,
    detail: (id: string) => [...queryKeys.pages.all, id] as const,
    workflows: (id: string) =>
      [...queryKeys.pages.all, id, "workflows"] as const,
  },
  plugins: {
    all: ["plugins"] as const,
    enrichments: (plugin: string, pageId: string) =>
      ["plugins", plugin, "enrichments", pageId] as const,
  },
  search: {
    all: ["search"] as const,
    text: (query: string, tags?: string[], tagMatchMode?: string) =>
      ["search", "text", query, tags, tagMatchMode] as const,
    summary: (query: string, tags?: string[], tagMatchMode?: string) =>
      ["search", "summary", query, tags, tagMatchMode] as const,
    hierarchical: (query: string, tags?: string[], tagMatchMode?: string) =>
      ["search", "hierarchical", query, tags, tagMatchMode] as const,
    compound: (smiles: string) => ["search", "compound", smiles] as const,
  },
  dashboard: {
    all: ["dashboard"] as const,
    stats: () => [...queryKeys.dashboard.all, "stats"] as const,
  },
  stats: {
    all: ["stats"] as const,
    workflows: () => [...queryKeys.stats.all, "workflows"] as const,
    pipeline: () => [...queryKeys.stats.all, "pipeline"] as const,
    vectors: () => [...queryKeys.stats.all, "vectors"] as const,
    tokenUsage: (period: string) => [...queryKeys.stats.all, "token-usage", period] as const,
    chatLatency: (period: string) => [...queryKeys.stats.all, "chat-latency", period] as const,
    searchQuality: (period: string) => [...queryKeys.stats.all, "search-quality", period] as const,
    grounding: (period: string) => [...queryKeys.stats.all, "grounding", period] as const,
    knowledgeGaps: (period: string) => [...queryKeys.stats.all, "knowledge-gaps", period] as const,
    citationFrequency: (period: string) => [...queryKeys.stats.all, "citation-frequency", period] as const,
  },
  user: {
    all: ["user"] as const,
    preferences: () => [...queryKeys.user.all, "preferences"] as const,
    activity: {
      searches: () => [...queryKeys.user.all, "activity", "searches"] as const,
      documents: () => [...queryKeys.user.all, "activity", "documents"] as const,
    },
  },
  chat: {
    all: ["chat"] as const,
    list: () => [...queryKeys.chat.all, "list"] as const,
    detail: (conversationId: string) =>
      [...queryKeys.chat.all, conversationId] as const,
    messages: (conversationId: string) =>
      [...queryKeys.chat.all, conversationId, "messages"] as const,
  },
  browse: {
    all: ["browse"] as const,
    categories: () => [...queryKeys.browse.all, "categories"] as const,
    folders: (entityType: string, parent?: string) =>
      [...queryKeys.browse.all, "folders", entityType, parent ?? "root"] as const,
    artifacts: (entityType: string, tagValue: string) =>
      [...queryKeys.browse.all, "artifacts", entityType, tagValue] as const,
    popularTags: (entityType?: string) =>
      [...queryKeys.browse.all, "popularTags", entityType ?? "all"] as const,
  },
};
