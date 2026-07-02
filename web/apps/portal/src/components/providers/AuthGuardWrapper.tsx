"use client";

import { useAuthz } from "@sentinel-auth/react";
import { ProgressSpinner } from "primereact/progressspinner";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { usePreferencesSync } from "@/hooks/use-preferences-sync";

/** Runs hooks that require authentication context. */
function AuthenticatedShell({ children }: { children: ReactNode }) {
  usePreferencesSync();
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
      <div className="flex h-screen items-center justify-center bg-surface-sunken">
        <ProgressSpinner
          style={{ width: "2rem", height: "2rem" }}
          strokeWidth="3"
        />
      </div>
    );
  }

  return <AuthenticatedShell>{children}</AuthenticatedShell>;
}
