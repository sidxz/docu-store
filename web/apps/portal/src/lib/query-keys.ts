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
    text: (query: string) => ["search", "text", query] as const,
    summary: (query: string) => ["search", "summary", query] as const,
    hierarchical: (query: string) =>
      ["search", "hierarchical", query] as const,
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
