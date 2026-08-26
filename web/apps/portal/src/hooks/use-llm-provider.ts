"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { authFetchJson } from "@/lib/auth-fetch";
import { queryKeys } from "@/lib/query-keys";

export type LlmProviderId = "openrouter" | "openai" | "gemini";

export interface LlmProviderPreset {
  model: string;
  chat_model: string;
}

/** GET /user/llm-provider — the key is write-only; only `key_last4` comes back. */
export interface LlmProviderStatus {
  enabled: boolean;
  configured: boolean;
  provider: LlmProviderId | null;
  key_last4: string | null;
  model: string | null;
  chat_model: string | null;
  presets: Record<LlmProviderId, LlmProviderPreset>;
}

/** PUT body. Omit `api_key` to change models only (the stored key is kept). */
export interface LlmProviderInput {
  provider: LlmProviderId;
  api_key?: string;
  model?: string;
  chat_model?: string;
}

export interface LlmLaneTestResult {
  ok: boolean;
  detail: string | null;
}

export interface LlmProviderTestResult {
  ok: boolean;
  lanes: Record<"batch" | "chat", LlmLaneTestResult>;
}

export function useLlmProvider() {
  return useQuery({
    queryKey: queryKeys.user.llmProvider(),
    queryFn: () => authFetchJson<LlmProviderStatus>("/user/llm-provider"),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

function useInvalidateProvider() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.user.llmProvider() });
}

export function useSaveLlmProvider() {
  const invalidate = useInvalidateProvider();
  return useMutation({
    mutationFn: (input: LlmProviderInput) =>
      authFetchJson<void>("/user/llm-provider", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      }),
    onSuccess: invalidate,
  });
}

export function useDeleteLlmProvider() {
  const invalidate = useInvalidateProvider();
  return useMutation({
    mutationFn: () => authFetchJson<void>("/user/llm-provider", { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

export function useTestLlmProvider() {
  return useMutation({
    mutationFn: () =>
      authFetchJson<LlmProviderTestResult>("/user/llm-provider/test", { method: "POST" }),
  });
}
