"use client";

import { useQuery } from "@tanstack/react-query";
import { authFetchJson } from "@/lib/auth-fetch";
import { queryKeys } from "@/lib/query-keys";
import type { UserTokenUsage } from "@docu-store/types";

/**
 * Total token usage across the current user's conversations + current-month block (topbar badge & usage page).
 * Includes: prompt + completion totals, monthly breakdown (chat/ingestion), and current month's limit.
 * Invalidated by use-chat's send onSuccess so it grows after each answer.
 */
export function useUserTokenUsage() {
  return useQuery({
    queryKey: queryKeys.chat.usage(),
    queryFn: () => authFetchJson<UserTokenUsage>("/chat/usage"),
    staleTime: 60_000,
  });
}
