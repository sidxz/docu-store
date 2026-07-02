"use client";

import { useQuery } from "@tanstack/react-query";
import { authFetchJson } from "@/lib/auth-fetch";
import { queryKeys } from "@/lib/query-keys";
import type { TokenUsage } from "@docu-store/types";

/**
 * Total token usage across the current user's conversations (topbar badge).
 * Invalidated by use-chat's send onSuccess so it grows after each answer.
 */
export function useUserTokenUsage() {
  return useQuery({
    queryKey: queryKeys.chat.usage(),
    queryFn: () => authFetchJson<TokenUsage>("/chat/usage"),
    staleTime: 60_000,
  });
}
