"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { authFetchJson } from "@/lib/auth-fetch";
import { queryKeys } from "@/lib/query-keys";

export interface WorkspaceChatSettings {
  answer_formatting: boolean;
  can_manage: boolean;
}

export function useWorkspaceChatSettings() {
  return useQuery({
    queryKey: queryKeys.workspace.chatSettings(),
    queryFn: () => authFetchJson<WorkspaceChatSettings>("/workspace/chat-settings"),
  });
}

export function useSetAnswerFormatting() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (on: boolean) =>
      authFetchJson<void>("/workspace/chat-settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer_formatting: on }),
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.workspace.chatSettings() }),
  });
}
