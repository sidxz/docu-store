"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AuthShell } from "@/components/auth/AuthShell";
import { AuthGuardWrapper } from "@/components/providers/AuthGuardWrapper";
import { useSaveLlmProvider } from "@/hooks/use-llm-provider";
import {
  clearOpenRouterVerifier,
  exchangeOpenRouterCode,
  takeOpenRouterReturnTo,
} from "@/lib/openrouter-pkce";

export default function OpenRouterCallbackPage() {
  return (
    <AuthGuardWrapper>
      {/* useSearchParams needs a Suspense boundary in Next 16 */}
      <Suspense fallback={null}>
        <Exchange />
      </Suspense>
    </AuthGuardWrapper>
  );
}

function Exchange() {
  const params = useSearchParams();
  const router = useRouter();
  const { mutateAsync: save } = useSaveLlmProvider();
  const [error, setError] = useState<string | null>(null);
  const [returnTo, setReturnTo] = useState("/onboarding");
  const started = useRef(false); // the code is single-use; guard StrictMode's double effect

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const dest = takeOpenRouterReturnTo();
    setReturnTo(dest);
    const code = params.get("code");
    if (!code) {
      clearOpenRouterVerifier();
      setError("OpenRouter returned no authorization code.");
      return;
    }
    (async () => {
      try {
        const key = await exchangeOpenRouterCode(code);
        await save({ provider: "openrouter", api_key: key });
        router.replace(dest);
      } catch (e) {
        setError(e instanceof Error ? e.message : "OpenRouter connection failed.");
      }
    })();
  }, [params, router, save]);

  return (
    <AuthShell>
      <div className="text-center">
        {error ? (
          <>
            <p className="mb-3 text-sm" style={{ color: "#b91c1c" }}>
              {error}
            </p>
            <a href={returnTo} className="text-sm underline" style={{ color: "#2563eb" }}>
              Back
            </a>
          </>
        ) : (
          <>
            <div className="mx-auto mb-3 h-6 w-6 animate-spin rounded-full border-2 border-[#e2e8f0] border-t-[#3b82f6]" />
            <p className="text-sm" style={{ color: "#64748b" }}>
              Connecting OpenRouter&hellip;
            </p>
          </>
        )}
      </div>
    </AuthShell>
  );
}
