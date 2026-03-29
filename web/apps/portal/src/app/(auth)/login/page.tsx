"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { FlaskConical } from "lucide-react";
import { useAuthz } from "@sentinel-auth/react";
import { useAppConfig } from "@/lib/app-config";
import { ShapeGrid } from "@/components/backgrounds/ShapeGrid";

export default function LoginPage() {
  const { login, isAuthenticated, isLoading } = useAuthz();
  const { googleClientId, githubClientId, entraIdClientId } = useAppConfig();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.replace("/");
    }
  }, [isAuthenticated, isLoading, router]);

  return (
    <div className="fixed inset-0 overflow-hidden" style={{ background: "#030712" }}>
      {/* Ambient glow — left-center for branding area */}
      <div
        className="absolute top-1/2 h-[600px] w-[600px] -translate-y-1/2"
        style={{
          left: "20%",
          background:
            "radial-gradient(circle, rgba(59, 130, 246, 0.08) 0%, transparent 70%)",
        }}
      />

      {/* Animated triangle grid */}
      <ShapeGrid />

      {/* Split layout */}
      <div className="relative z-10 flex min-h-screen">
        {/* Left: Branding — desktop only */}
        <div
          className="hidden flex-1 flex-col justify-between p-12 md:flex xl:p-16"
          style={{ animation: "auth-enter 0.7s ease-out 0.3s both" }}
        >
          <div />

          <div>
            <div
              className="flex h-14 w-14 items-center justify-center rounded-2xl"
              style={{
                background: "rgba(59, 130, 246, 0.12)",
                boxShadow: "0 0 30px rgba(59, 130, 246, 0.2)",
              }}
            >
              <FlaskConical className="h-7 w-7" style={{ color: "#60a5fa" }} />
            </div>

            <h1
              className="mt-6 text-4xl font-bold"
              style={{ color: "#f1f5f9", letterSpacing: "0.06em" }}
            >
              DocuStore
            </h1>

            <div
              className="mt-4 h-px w-12"
              style={{ background: "rgba(59, 130, 246, 0.4)" }}
            />

            <p
              className="mt-4 max-w-xs text-lg leading-relaxed"
              style={{ color: "#64748b" }}
            >
              Document intelligence
              <br />
              for drug discovery
            </p>
          </div>

          <div style={{ animation: "auth-enter 0.7s ease-out 0.5s both" }}>
            <a
              href="https://docustore.io"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm transition-colors hover:underline"
              style={{ color: "#475569" }}
            >
              docustore.io
            </a>
            <p className="mt-1 text-xs" style={{ color: "#1e293b" }}>
              &copy; 2026 DocuStore. All rights reserved.
            </p>
          </div>
        </div>

        {/* Right: Login panel */}
        <div
          className="relative flex w-full flex-shrink-0 items-center justify-center px-8 md:w-[460px]"
          style={{
            background: "rgba(8, 14, 27, 0.95)",
          }}
        >
          {/* Left edge line — desktop only */}
          <div
            className="absolute inset-y-0 left-0 hidden w-px md:block"
            style={{ background: "rgba(148, 163, 184, 0.06)" }}
          />

          <div className="w-full max-w-[320px]">
            {/* Mobile-only brand header */}
            <div
              className="mb-10 flex flex-col items-center md:hidden"
              style={{ animation: "auth-enter 0.6s ease-out 0.05s both" }}
            >
              <div
                className="flex h-12 w-12 items-center justify-center rounded-xl"
                style={{
                  background: "rgba(59, 130, 246, 0.12)",
                  boxShadow: "0 0 24px rgba(59, 130, 246, 0.2)",
                }}
              >
                <FlaskConical
                  className="h-6 w-6"
                  style={{ color: "#60a5fa" }}
                />
              </div>
              <h1
                className="mt-3 text-xl font-semibold"
                style={{ color: "#f1f5f9", letterSpacing: "0.08em" }}
              >
                DocuStore
              </h1>
              <p className="mt-1 text-sm" style={{ color: "#64748b" }}>
                Document intelligence for drug discovery
              </p>
            </div>

            {/* Desktop: Sign-in header */}
            <div
              className="mb-8 hidden md:block"
              style={{ animation: "auth-enter 0.6s ease-out 0.1s both" }}
            >
              <h2
                className="text-xl font-semibold"
                style={{ color: "#f1f5f9" }}
              >
                Sign in
              </h2>
              <p className="mt-1 text-sm" style={{ color: "#64748b" }}>
                to continue to DocuStore
              </p>
            </div>

            {/* OAuth buttons */}
            <div className="space-y-3">
              {/* Google */}
              <button
                disabled={!googleClientId}
                onClick={() => login("google")}
                className="flex w-full cursor-pointer items-center justify-center gap-3 rounded-xl px-4 py-2.5 text-sm font-medium transition-all duration-200 hover:-translate-y-px hover:shadow-lg active:translate-y-0"
                style={{
                  background: "rgba(255, 255, 255, 0.95)",
                  color: "#1f2937",
                  animation: "auth-enter 0.5s ease-out 0.2s both",
                }}
              >
                <GoogleIcon />
                Continue with Google
              </button>

              {/* GitHub */}
              <button
                disabled={!githubClientId}
                onClick={() => login("github")}
                className="flex w-full cursor-pointer items-center justify-center gap-3 rounded-xl px-4 py-2.5 text-sm font-medium transition-all duration-200 hover:-translate-y-px hover:shadow-lg active:translate-y-0"
                style={{
                  background: "#161b22",
                  color: "#ffffff",
                  animation: "auth-enter 0.5s ease-out 0.25s both",
                }}
              >
                <GitHubIcon />
                Continue with GitHub
              </button>

              {/* Entra ID (disabled) */}
              <button
                disabled={!entraIdClientId}
                className="flex w-full cursor-not-allowed items-center justify-center gap-3 rounded-xl border px-4 py-2.5 text-sm font-medium opacity-40"
                style={{
                  background: "rgba(30, 41, 59, 0.4)",
                  color: "#94a3b8",
                  borderColor: "rgba(148, 163, 184, 0.06)",
                  animation: "auth-enter 0.5s ease-out 0.3s both",
                }}
              >
                <MicrosoftIcon />
                Continue with Entra ID
              </button>
            </div>

            {/* Footer */}
            <p
              className="mt-6 text-center text-xs"
              style={{
                color: "#475569",
                animation: "auth-enter 0.5s ease-out 0.35s both",
              }}
            >
              
            </p>

            {/* Mobile-only: footer */}
            <div
              className="mt-10 text-center md:hidden"
              style={{ animation: "auth-enter 0.5s ease-out 0.4s both" }}
            >
              <a
                href="https://docustore.io"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs transition-colors hover:underline"
                style={{ color: "#475569" }}
              >
                docustore.io
              </a>
              <p className="mt-1 text-xs" style={{ color: "#1e293b" }}>
                &copy; 2026 DocuStore
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24">
      <path
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
        fill="#4285F4"
      />
      <path
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
        fill="#34A853"
      />
      <path
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
        fill="#FBBC05"
      />
      <path
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
        fill="#EA4335"
      />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg
      className="h-[18px] w-[18px]"
      viewBox="0 0 24 24"
      fill="currentColor"
    >
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0 0 22 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  );
}

function MicrosoftIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 21 21">
      <rect x="1" y="1" width="9" height="9" fill="#f25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
      <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
      <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
    </svg>
  );
}
