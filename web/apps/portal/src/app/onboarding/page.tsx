"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { AuthShell } from "@/components/auth/AuthShell";
import { AuthGuardWrapper } from "@/components/providers/AuthGuardWrapper";
import { LlmProviderForm } from "@/components/settings/LlmProviderForm";
import { LogoMark } from "@/components/ui/LogoMark";
import { Button } from "@/components/ui/button";
import { skipLlmOnboarding } from "@/hooks/use-llm-onboarding-gate";
import { useLlmProvider } from "@/hooks/use-llm-provider";
import { useSession } from "@/lib/auth";

export default function OnboardingPage() {
  return (
    <AuthGuardWrapper>
      <Onboarding />
    </AuthGuardWrapper>
  );
}

function Onboarding() {
  const router = useRouter();
  const { workspace } = useSession();
  const provider = useLlmProvider();
  const home = workspace.slug ? `/${workspace.slug}` : "/";

  // Not a BYO deployment → nothing to onboard.
  useEffect(() => {
    if (provider.data && !provider.data.enabled) router.replace(home);
  }, [provider.data, home, router]);

  return (
    <AuthShell>
      <div
        className="w-full max-w-xl border bg-white p-8 shadow-sm"
        style={{ borderColor: "#e2e8f0", animation: "auth-enter 0.5s ease-out both" }}
      >
        <div className="mb-6 flex items-center gap-3" style={{ color: "#0f172a" }}>
          <LogoMark className="h-8 w-8" />
          <h1 className="text-xl font-medium">Connect your LLM</h1>
        </div>
        <p className="mb-6 text-sm" style={{ color: "#475569" }}>
          DocuStore runs on your own model account — you pay your provider directly and we
          never see your spend. Reading and search work without one; uploads and chat need it.
        </p>
        <LlmProviderForm onConfigured={() => router.replace(home)} />
        {provider.data?.configured ? (
          <Button className="mt-6" onClick={() => router.replace(home)}>
            Continue to DocuStore
          </Button>
        ) : (
          <button
            type="button"
            className="mt-6 text-sm underline"
            style={{ color: "#64748b" }}
            onClick={() => {
              skipLlmOnboarding();
              router.replace(home);
            }}
          >
            Skip for now
          </button>
        )}
      </div>
    </AuthShell>
  );
}
