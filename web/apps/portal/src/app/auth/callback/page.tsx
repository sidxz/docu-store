"use client";

import { useRouter } from "next/navigation";
import { AuthzCallback } from "@duar-auth/react";
import { AuthShell } from "@/components/auth/AuthShell";
import { forgetWorkspace } from "@/lib/workspace-memory";
import { useAppConfig } from "@/lib/app-config";
import { onboardUrl } from "@/lib/onboard";
import { LogoMark } from "@/components/ui/LogoMark";
import { WorkspaceSelector } from "./workspace-selector";

// Wordmark is always the brand font, regardless of the user's app font setting
const wordmark = {
  fontFamily: "var(--font-overused-grotesk), ui-sans-serif, sans-serif",
};

export default function AuthCallbackPage() {
  const router = useRouter();
  const { duarUrl, selfServeEnabled } = useAppConfig();

  return (
    <AuthzCallback
      onSuccess={(user, returnTo) => {
        // A stale returnTo (e.g. captured in another tab before a workspace
        // switch) must not land this workspace's token on another workspace's
        // URLs — honor it only inside the entered workspace. Onboarding routes
        // are workspace-agnostic (the authz token carries the workspace) and
        // are honored too — e.g. the OpenRouter PKCE callback's returnTo after
        // a silent re-auth.
        const home = `/${user.workspaceSlug}`;
        const onboarding =
          returnTo === "/onboarding" || returnTo?.startsWith("/onboarding/");
        const dest =
          returnTo === home || returnTo?.startsWith(`${home}/`) || onboarding
            ? (returnTo ?? home)
            : home;
        router.replace(dest);
      }}
      onError={() => {
        // A failed auto-entry must not loop — forget the remembered workspace
        // so the next sign-in shows the picker again (errorComponent still renders).
        forgetWorkspace();
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
      errorComponent={(error) => {
        // Matches the zero-workspace error thrown by @duar-auth/react
        // (sdks/react/src/authz-callback.tsx: "No workspaces available. …").
        // If the SDK copy changes, the raw message + "Back to login" still render.
        const noWorkspace =
          selfServeEnabled && error.message.startsWith("No workspaces available");
        return (
          <AuthShell>
            <div
              className="w-full max-w-md border bg-white p-10 text-center"
              style={{
                borderColor: "#e2e8f0",
                animation: "auth-enter 0.6s ease-out forwards",
              }}
            >
              {noWorkspace ? (
                <>
                  <LogoMark className="mx-auto mb-6 h-10 w-10" />
                  <h1
                    className="text-2xl"
                    style={{ ...wordmark, color: "#0f172a", fontWeight: 500, letterSpacing: "-0.02em" }}
                  >
                    You&rsquo;re not part of a workspace yet.
                  </h1>
                  <h2 className="mt-3 text-base font-normal" style={{ color: "#475569" }}>
                    Join your group or create a new one.
                  </h2>
                  <a
                    href={onboardUrl(duarUrl)}
                    className="mt-8 flex h-11 w-full items-center justify-center rounded-none px-4 text-sm font-medium text-white transition-colors"
                    style={{ background: "#0f172a" }}
                  >
                    Join or create a workspace
                  </a>
                </>
              ) : (
                <p className="mb-4 text-sm" style={{ color: "#dc2626" }}>
                  {error.message}
                </p>
              )}
              <a
                href="/login"
                className="mt-4 block text-sm transition-colors hover:underline"
                style={{ color: "#64748b" }}
              >
                Back to login
              </a>
            </div>
          </AuthShell>
        );
      }}
      workspaceSelector={(props) => (
        <AuthShell>
          <WorkspaceSelector {...props} />
        </AuthShell>
      )}
    />
  );
}
