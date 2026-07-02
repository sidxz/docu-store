"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { AuthzCallback } from "@sentinel-auth/react";
import { ShapeGrid } from "@/components/backgrounds/ShapeGrid";

export default function AuthCallbackPage() {
  const router = useRouter();

  return (
    <AuthzCallback
      onSuccess={(user, returnTo) =>
        router.replace(returnTo ?? `/${user.workspaceSlug}`)
      }
      onSilentReauthFailed={() => router.replace("/login")}
      loadingComponent={
        <AuthShell>
          <div className="text-center">
            <div className="mx-auto mb-3 h-6 w-6 animate-spin rounded-full border-2 border-[#334155] border-t-[#60a5fa]" />
            <p className="text-sm" style={{ color: "#64748b" }}>
              Signing you in&hellip;
            </p>
          </div>
        </AuthShell>
      }
      errorComponent={(error) => (
        <AuthShell>
          <div
            className="w-full max-w-sm rounded-2xl border p-8 text-center"
            style={{
              background: "rgba(15, 23, 42, 0.5)",
              borderColor: "rgba(148, 163, 184, 0.08)",
              backdropFilter: "blur(24px)",
              animation: "auth-enter 0.6s ease-out forwards",
            }}
          >
            <p className="mb-4 text-sm" style={{ color: "#ef4444" }}>
              {error.message}
            </p>
            <a
              href="/login"
              className="text-sm underline transition-colors"
              style={{ color: "#60a5fa" }}
            >
              Back to login
            </a>
          </div>
        </AuthShell>
      )}
      workspaceSelector={({ workspaces, onSelect, isLoading }) => (
        <AuthShell>
          <div className="w-full max-w-sm">
            <h2
              className="mb-6 text-center text-lg font-semibold"
              style={{
                color: "#f1f5f9",
                animation: "auth-enter 0.6s ease-out 0.1s both",
              }}
            >
              Select Workspace
            </h2>
            <div className="space-y-2">
              {workspaces.map((ws, i) => (
                <button
                  key={ws.id}
                  onClick={() => onSelect(ws.id)}
                  disabled={isLoading}
                  className="w-full rounded-xl border p-4 text-left transition-all duration-200 hover:-translate-y-px hover:shadow-lg disabled:opacity-50"
                  style={{
                    background: "rgba(15, 23, 42, 0.5)",
                    borderColor: "rgba(148, 163, 184, 0.08)",
                    backdropFilter: "blur(24px)",
                    animation: `auth-enter 0.5s ease-out ${0.15 + i * 0.05}s both`,
                  }}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div
                        className="font-medium"
                        style={{ color: "#f1f5f9" }}
                      >
                        {ws.name}
                      </div>
                      <div className="text-xs" style={{ color: "#64748b" }}>
                        {ws.slug}
                      </div>
                    </div>
                    <span
                      className="rounded-full px-2 py-0.5 text-xs font-medium"
                      style={{
                        background: "rgba(59, 130, 246, 0.15)",
                        color: "#60a5fa",
                      }}
                    >
                      {ws.role}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </AuthShell>
      )}
    />
  );
}

function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="fixed inset-0 overflow-hidden" style={{ background: "#030712" }}>
      <div
        className="absolute left-1/2 top-1/2 h-[600px] w-[600px] -translate-x-1/2 -translate-y-1/2 rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(59, 130, 246, 0.08) 0%, transparent 70%)",
        }}
      />
      <ShapeGrid />
      <div className="relative z-10 flex min-h-screen items-center justify-center px-4">
        {children}
      </div>
    </div>
  );
}
