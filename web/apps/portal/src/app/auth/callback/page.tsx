"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { AuthzCallback } from "@sentinel-auth/react";
import { ShapeGrid } from "@/components/backgrounds/ShapeGrid";
import { WorkspaceSelector } from "./workspace-selector";

export default function AuthCallbackPage() {
  const router = useRouter();

  return (
    <AuthzCallback
      onSuccess={(user, returnTo) => {
        // A stale returnTo (e.g. captured in another tab before a workspace
        // switch) must not land this workspace's token on another workspace's
        // URLs — honor it only inside the entered workspace.
        const home = `/${user.workspaceSlug}`;
        const dest = returnTo === home || returnTo?.startsWith(`${home}/`) ? returnTo : home;
        router.replace(dest);
      }}
      onSilentReauthFailed={() => router.replace("/login")}
      loadingComponent={
        <AuthShell>
          <div className="text-center">
            <div className="mx-auto mb-3 h-6 w-6 animate-spin rounded-full border-2 border-[#e2e8f0] border-t-[#3b82f6]" />
            <p className="text-sm" style={{ color: "#64748b" }}>
              Signing you in&hellip;
            </p>
          </div>
        </AuthShell>
      }
      errorComponent={(error) => (
        <AuthShell>
          <div
            className="w-full max-w-sm rounded-xl border bg-white p-8 text-center"
            style={{
              borderColor: "#e2e8f0",
              animation: "auth-enter 0.6s ease-out forwards",
            }}
          >
            <p className="mb-4 text-sm" style={{ color: "#dc2626" }}>
              {error.message}
            </p>
            <a
              href="/login"
              className="text-sm underline transition-colors"
              style={{ color: "#2563eb" }}
            >
              Back to login
            </a>
          </div>
        </AuthShell>
      )}
      workspaceSelector={(props) => (
        <AuthShell>
          <WorkspaceSelector {...props} />
        </AuthShell>
      )}
    />
  );
}

function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="fixed inset-0 overflow-hidden" style={{ background: "#f6f8fb" }}>
      <ShapeGrid />
      <div className="relative z-10 flex min-h-screen items-center justify-center px-4">
        {children}
      </div>
    </div>
  );
}
