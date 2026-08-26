"use client";

import { useAuthz } from "@duar-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { useLlmOnboardingGate } from "@/hooks/use-llm-onboarding-gate";
import { usePreferencesSync } from "@/hooks/use-preferences-sync";

/** Runs hooks that require authentication context. */
function AuthenticatedShell({ children }: { children: ReactNode }) {
  usePreferencesSync();
  useLlmOnboardingGate();
  return <>{children}</>;
}

/**
 * Route guard. Only bounces to /login when the session is truly gone
 * (`unauthenticated`). During `needs_reauth` — a valid authz token but the
 * memory-only IdP token lost on reload — we hold the spinner while the
 * AuthzProvider's `autoReauth` performs a silent (prompt=none) re-auth;
 * redirecting here would pre-empt it and cause the old reload-to-login bounce.
 */
export function AuthGuardWrapper({ children }: { children: ReactNode }) {
  const { authState, isLoading } = useAuthz();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && authState === "unauthenticated") {
      router.replace("/login");
    }
  }, [isLoading, authState, router]);

  if (isLoading || authState !== "authenticated") {
    return (
      <LoadingSpinner
        size="lg"
        className="flex h-screen items-center justify-center bg-surface-sunken"
      />
    );
  }

  return <AuthenticatedShell>{children}</AuthenticatedShell>;
}
