"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthz } from "@sentinel-auth/react";

/**
 * Root page — auth-aware redirect.
 *
 * Authenticated users go to their workspace; others to /login.
 */
export default function RootPage() {
  const { authState, isLoading, client } = useAuthz();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;
    if (authState === "authenticated") {
      const user = client.getUser();
      router.replace(`/${user?.workspaceSlug ?? "default"}`);
    } else if (authState === "unauthenticated") {
      router.replace("/login");
    }
    // needs_reauth: hold — AuthzProvider's autoReauth silently re-auths.
  }, [authState, isLoading, client, router]);

  return (
    <div className="flex h-screen items-center justify-center bg-surface-sunken">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-border-default border-t-accent" />
    </div>
  );
}
