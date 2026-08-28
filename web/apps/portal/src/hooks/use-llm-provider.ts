"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { authFetchJson } from "@/lib/auth-fetch";
import { queryKeys } from "@/lib/query-keys";

export type LlmProviderId = "openrouter" | "openai" | "gemini";

export interface LlmProviderPreset {
  model: string;
  chat_model: string;
}

/** One configured provider. Exactly one of them is `active`. */
export interface LlmProviderEntry {
  provider: LlmProviderId;
  model: string;
  chat_model: string;
  key_last4: string;
  active: boolean;
  updated_at: string | null;
}

/** GET /user/llm-provider — keys are write-only; only `key_last4` comes back. */
export interface LlmProviderStatus {
  enabled: boolean;
  /** An active provider exists — i.e. there is something to run on. */
  configured: boolean;
  providers: LlmProviderEntry[];
  presets: Record<LlmProviderId, LlmProviderPreset>;
  /** Model names to offer per provider — a hint, not a contract. Empty for
   *  OpenRouter, and absent altogether from a backend older than this field. */
  suggestions?: Record<LlmProviderId, string[]>;
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
  lanes: Record<"batch" | "chat" | "ner", LlmLaneTestResult>;
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
    mutationFn: (provider: LlmProviderId) =>
      authFetchJson<void>(`/user/llm-provider/${provider}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

/** Switch what everything runs on. Refused if the model cannot do entity extraction. */
export function useActivateLlmProvider() {
  const invalidate = useInvalidateProvider();
  return useMutation({
    mutationFn: (provider: LlmProviderId) =>
      authFetchJson<void>(`/user/llm-provider/${provider}/activate`, { method: "POST" }),
    onSuccess: invalidate,
  });
}

/**
 * Probe any stored provider, active or not — the point is to find out before
 * switching. `model`/`chat_model` override what is stored, so the form can test
 * what is typed; blanks resolve to the preset exactly as a save would. The key
 * is never sent, only ever the stored one.
 */
export function useTestLlmProvider() {
  return useMutation({
    mutationFn: ({
      provider,
      ...models
    }: {
      provider: LlmProviderId;
      model?: string;
      chat_model?: string;
    }) =>
      authFetchJson<LlmProviderTestResult>(`/user/llm-provider/${provider}/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(models),
      }),
  });
}
