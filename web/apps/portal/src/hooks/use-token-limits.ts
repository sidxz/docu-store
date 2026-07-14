"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { authFetch, authFetchJson } from "@/lib/auth-fetch";
import { queryKeys } from "@/lib/query-keys";

export interface TokenLimitOverride {
  user_id: string;
  limit: number | null;
}

export interface WorkspaceTokenLimits {
  default_limit: number | null;
  overrides: TokenLimitOverride[];
}

/** PUT/DELETE return 204 (no body) — authFetchJson would choke on the empty body. */
async function limitRequest(path: string, init: RequestInit): Promise<void> {
  const res = await authFetch(path, init);
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // non-JSON error body
    }
    throw new Error(detail ?? `Request failed (${res.status})`);
  }
}

export function useWorkspaceTokenLimits() {
  return useQuery({
    queryKey: queryKeys.workspace.tokenLimits(),
    queryFn: () => authFetchJson<WorkspaceTokenLimits>("/workspace/token-limits"),
  });
}

function useInvalidateLimits() {
  const queryClient = useQueryClient();
  return () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.workspace.tokenLimits() });
}

export function useSetDefaultTokenLimit() {
  const invalidate = useInvalidateLimits();
  return useMutation({
    mutationFn: (limit: number | null) =>
      limitRequest("/workspace/token-limits/default", {
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
      limitRequest(`/workspace/token-limits/${userId}`, {
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
      limitRequest(`/workspace/token-limits/${userId}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}
