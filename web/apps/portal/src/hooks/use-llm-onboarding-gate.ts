"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { useLlmProvider } from "@/hooks/use-llm-provider";

const SKIP_KEY = "ds-llm-onboarding-skipped";

/** "Skip for now": suppress the redirect for this browser session only. */
export function skipLlmOnboarding(): void {
  try {
    sessionStorage.setItem(SKIP_KEY, "1");
  } catch {
    // storage unavailable — the redirect simply repeats
  }
}

function skipped(): boolean {
  try {
    return sessionStorage.getItem(SKIP_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * First-run gate: BYO-LLM mode on + no provider for this user → /onboarding.
 * Fails open when the status query errors (data undefined). The onboarding
 * routes themselves are exempt so the PKCE callback can finish.
 */
export function useLlmOnboardingGate(): void {
  const { data } = useLlmProvider();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!data?.enabled || data.configured) return;
    if (pathname.startsWith("/onboarding") || skipped()) return;
    router.replace("/onboarding");
  }, [data, pathname, router]);
}
