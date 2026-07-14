"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { authFetchJson } from "@/lib/auth-fetch";
import { queryKeys } from "@/lib/query-keys";

export interface TokenLimitOverride {
  user_id: string;
  limit: number | null;
}

export interface WorkspaceTokenLimits {
  default_limit: number | null;
  overrides: TokenLimitOverride[];
}

export function useWorkspaceTokenLimits() {
  return useQuery({
    queryKey: queryKeys.workspace.tokenLimits(),
    queryFn: () => authFetchJson<WorkspaceTokenLimits>("/workspace/token-limits"),
  });
}

function useInvalidateLimits() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.workspace.tokenLimits() });
    queryClient.invalidateQueries({ queryKey: queryKeys.chat.usage() });
  };
}

export function useSetDefaultTokenLimit() {
  const invalidate = useInvalidateLimits();
  return useMutation({
    mutationFn: (limit: number | null) =>
      authFetchJson<void>("/workspace/token-limits/default", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit }),
      }),
    onSuccess: invalidate,
  });
}

export function useSetUserTokenLimit() {
  const invalidate = useInvalidateLimits();
  return useMutation({
    mutationFn: ({ userId, limit }: { userId: string; limit: number | null }) =>
      authFetchJson<void>(`/workspace/token-limits/${userId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit }),
      }),
    onSuccess: invalidate,
  });
}

export function useClearUserTokenLimit() {
  const invalidate = useInvalidateLimits();
  return useMutation({
    mutationFn: (userId: string) =>
      authFetchJson<void>(`/workspace/token-limits/${userId}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}
