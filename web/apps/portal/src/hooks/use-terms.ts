"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { authFetchJson } from "@/lib/auth-fetch";
import { queryKeys } from "@/lib/query-keys";

/** GET /user/terms — `required` is false on non-self-serve deployments. */
export interface TermsStatus {
  required: boolean;
  current_version: string;
  accepted_version: string | null;
  accepted_at: string | null;
}

export const TERMS_ROUTE = "/onboarding/terms";

export function useTerms() {
  return useQuery({
    queryKey: queryKeys.user.terms(),
    queryFn: () => authFetchJson<TermsStatus>("/user/terms"),
    staleTime: Infinity,
    retry: 1,
  });
}

export function useAcceptTerms() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (version: string) =>
      authFetchJson<TermsStatus>("/user/terms/accept", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version }),
      }),
    onSuccess: (data) => qc.setQueryData(queryKeys.user.terms(), data),
  });
}

/**
 * First-run gate: public edition + this user has not accepted the current
 * Terms/Privacy version → /onboarding/terms, with no way past it.
 *
 * Deliberately a hard gate, unlike the LLM onboarding gate: there is no "skip
 * for now", because the point is that nothing happens before acceptance. Must
 * run BEFORE useLlmOnboardingGate so nobody is asked for an API key first.
 *
 * Fails open when the status query errors (data undefined) — an outage should
 * not lock everyone out. The upload route enforces server-side regardless.
 */
export function useTermsGate(): void {
  const { data } = useTerms();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!data?.required) return;
    if (pathname === TERMS_ROUTE) return;
    router.replace(TERMS_ROUTE);
  }, [data, pathname, router]);
}
