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
  },
  pages: {
    all: ["pages"] as const,
    list: (artifactId: string) =>
      [...queryKeys.pages.all, "list", artifactId] as const,
    detail: (id: string) => [...queryKeys.pages.all, id] as const,
    workflows: (id: string) =>
      [...queryKeys.pages.all, id, "workflows"] as const,
  },
  search: {
    text: (query: string) => ["search", "text", query] as const,
    summary: (query: string) => ["search", "summary", query] as const,
    hierarchical: (query: string) =>
      ["search", "hierarchical", query] as const,
    compound: (smiles: string) => ["search", "compound", smiles] as const,
  },
};
