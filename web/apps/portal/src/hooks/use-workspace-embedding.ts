"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { authFetchJson } from "@/lib/auth-fetch";
import { queryKeys } from "@/lib/query-keys";

export interface EmbeddingModelOption {
  id: string;
  label: string;
  /** BYO-LLM provider ids whose key can serve this model. */
  providers: string[];
}

/** GET /workspace/embedding — self-serve only (`enabled`). */
export interface WorkspaceEmbedding {
  enabled: boolean;
  /** "local" (the server's own model) or an option id. */
  model: string;
  server_model: string;
  /** Changing the model then re-embeds every document. */
  has_documents: boolean;
  /** The caller holds a key that can serve `model`. */
  usable: boolean;
  detail: string | null;
  options: EmbeddingModelOption[];
}

export const LOCAL_EMBEDDING_MODEL = "local";

export function useWorkspaceEmbedding() {
  return useQuery({
    queryKey: queryKeys.workspace.embedding(),
    queryFn: () => authFetchJson<WorkspaceEmbedding>("/workspace/embedding"),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

export function useSetWorkspaceEmbedding() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { model: string; reembed: boolean }) =>
      authFetchJson<{ model: string; reembed_workflows: number }>("/workspace/embedding", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.workspace.embedding() }),
  });
}
