"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthz } from "@duar-auth/react";
import { useAppConfig } from "@/lib/app-config";
import { onboardUrl } from "@/lib/onboard";
import { ShapeGrid } from "@/components/backgrounds/ShapeGrid";
import { LogoMark } from "@/components/ui/LogoMark";

// Wordmark is always the brand font, regardless of the user's app font setting
const wordmark = {
  fontFamily: "var(--font-overused-grotesk), ui-sans-serif, sans-serif",
};

// docustore.io button shape (sharp, flat hovers), app typography (Plex Sans)
const btnBase =
  "flex h-11 w-full items-center justify-center gap-3 rounded-none px-4 text-sm font-medium transition-colors";

export default function LoginPage() {
  const { login, isAuthenticated, isLoading } = useAuthz();
  const { googleClientId, githubClientId, entraIdClientId, duarUrl, appUrl, selfServeEnabled } =
    useAppConfig();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.replace("/");
    }
  }, [isAuthenticated, isLoading, router]);

  return (
    <div className="fixed inset-0 overflow-hidden" style={{ background: "#f6f8fb" }}>
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
            {/* Site logo lockup at hero scale: bare mark left, .io muted to 30% ink */}
            <div className="flex items-center gap-3" style={{ color: "#0f172a" }}>
              <LogoMark className="h-12 w-12 xl:h-14 xl:w-14" />
              <h1
                className="text-4xl xl:text-5xl"
                style={{ ...wordmark, fontWeight: 500, letterSpacing: "-0.02em" }}
              >
                DocuStore
                <span style={{ color: "rgba(15, 23, 42, 0.3)" }}>.io</span>
              </h1>
            </div>

            <div
              className="mt-5 h-[1.5px] w-14"
              style={{ background: "linear-gradient(90deg, #37d7fa, #4b72fe)" }}
            />

            <p
              className="mt-5 max-w-xs text-xl leading-relaxed"
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
              style={{ color: "#64748b" }}
            >
              docustore.io
            </a>
            <p className="mt-1 text-xs" style={{ color: "#94a3b8" }}>
              &copy; 2026 DocuStore. All rights reserved.
            </p>
          </div>
        </div>

        {/* Right: Login panel */}
        <div
          className="relative flex w-full flex-shrink-0 items-center justify-center px-8 md:w-[460px]"
          style={{ background: "rgba(255, 255, 255, 0.94)" }}
        >
          {/* Left edge line — desktop only */}
          <div
            className="absolute inset-y-0 left-0 hidden w-px md:block"
            style={{ background: "#e2e8f0" }}
          />

          <div className="w-full max-w-[320px]">
            {/* Mobile-only brand header */}
            <div
              className="mb-10 flex flex-col items-center md:hidden"
              style={{ animation: "auth-enter 0.6s ease-out 0.05s both" }}
            >
              <div className="flex items-center gap-2" style={{ color: "#0f172a" }}>
                <LogoMark className="h-9 w-9" />
                <h1
                  className="text-2xl"
                  style={{ ...wordmark, fontWeight: 500, letterSpacing: "-0.02em" }}
                >
                  DocuStore
                  <span style={{ color: "rgba(15, 23, 42, 0.3)" }}>.io</span>
                </h1>
              </div>
              <p className="mt-1 text-sm" style={{ color: "#64748b" }}>
                Document intelligence for drug discovery
              </p>
            </div>

            {/* Desktop: Sign-in header */}
            <div
              className="mb-8 hidden md:block"
              style={{ animation: "auth-enter 0.6s ease-out 0.1s both" }}
            >
              <h2 className="text-xl font-semibold" style={{ color: "#0f172a" }}>
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
                className={`${btnBase} cursor-pointer border border-[#0f172a] bg-white text-[#0f172a] hover:bg-[#f1f5f9]`}
                style={{ animation: "auth-enter 0.5s ease-out 0.2s both" }}
              >
                <GoogleIcon />
                Continue with Google
              </button>

              {/* GitHub */}
              <button
                disabled={!githubClientId}
                onClick={() => login("github")}
                className={`${btnBase} cursor-pointer bg-[#0f172a] text-white hover:opacity-85`}
                style={{ animation: "auth-enter 0.5s ease-out 0.25s both" }}
              >
                <GitHubIcon />
                Continue with GitHub
              </button>

              {/* Entra ID (disabled) */}
              <button
                disabled={!entraIdClientId}
                className={`${btnBase} cursor-not-allowed border border-[#e2e8f0] bg-white text-[#94a3b8] opacity-60`}
                style={{ animation: "auth-enter 0.5s ease-out 0.3s both" }}
              >
                <MicrosoftIcon />
                Continue with Entra ID
              </button>
            </div>

            {selfServeEnabled && (
              <p
                className="mt-6 text-center text-sm"
                style={{ color: "#64748b", animation: "auth-enter 0.5s ease-out 0.35s both" }}
              >
                New here?{" "}
                <a
                  href={onboardUrl(duarUrl, appUrl)}
                  className="underline transition-colors"
                  style={{ color: "#2563eb" }}
                >
                  Sign up or join a workspace
                </a>
              </p>
            )}

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
                style={{ color: "#64748b" }}
              >
                docustore.io
              </a>
              <p className="mt-1 text-xs" style={{ color: "#94a3b8" }}>
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
