"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthShell } from "@/components/auth/AuthShell";
import { AuthGuardWrapper } from "@/components/providers/AuthGuardWrapper";
import { LogoMark } from "@/components/ui/LogoMark";
import { Button } from "@/components/ui/button";
import { useAcceptTerms, useTerms } from "@/hooks/use-terms";
import { useSession } from "@/lib/auth";

const SITE = "https://docustore.io";

export default function TermsPage() {
  return (
    <AuthGuardWrapper>
      <Terms />
    </AuthGuardWrapper>
  );
}

function Terms() {
  const router = useRouter();
  const { workspace } = useSession();
  const { data } = useTerms();
  const accept = useAcceptTerms();
  const [agreed, setAgreed] = useState(false);
  const home = workspace.slug ? `/${workspace.slug}` : "/";

  // Nothing to accept (already accepted, or not a public deployment) → move on.
  useEffect(() => {
    if (data && !data.required) router.replace(home);
  }, [data, home, router]);

  const link = "underline underline-offset-2";

  return (
    <AuthShell>
      <div
        className="w-full max-w-xl border bg-white p-8 shadow-sm"
        style={{ borderColor: "#e2e8f0", animation: "auth-enter 0.5s ease-out both" }}
      >
        <div className="mb-6 flex items-center gap-3" style={{ color: "#0f172a" }}>
          <LogoMark className="h-8 w-8" />
          <h1 className="text-xl font-medium">Before you start</h1>
        </div>

        <p className="text-sm" style={{ color: "#475569" }}>
          DocuStore Cloud is a free <strong style={{ color: "#0f172a" }}>research preview</strong>.
          Two things are worth knowing before you upload anything:
        </p>

        <ul className="mt-4 space-y-3 text-sm" style={{ color: "#475569" }}>
          <li className="flex gap-2">
            <span aria-hidden style={{ color: "#94a3b8" }}>
              &bull;
            </span>
            <span>
              <strong style={{ color: "#0f172a" }}>
                Your documents are sent to an AI provider that you have configured.
              </strong>{" "}
              On DocuStore Cloud you connect your own AI provider, such as OpenRouter or
              OpenAI, and that connection remains your responsibility. When you chat or run
              enrichment, excerpts of your documents are sent to the provider you connected,
              and their terms govern how they handle that content. Please do not upload
              patient data, confidential material, or anything you are not licensed to
              share.
            </span>
          </li>
          <li className="flex gap-2">
            <span aria-hidden style={{ color: "#94a3b8" }}>
              &bull;
            </span>
            <span>
              <strong style={{ color: "#0f172a" }}>DocuStore can make mistakes.</strong>{" "}
              Structures, identifiers, values, and citations are produced by automated
              recognition and language models, so please verify them against the source
              document before relying on them.
            </span>
          </li>
        </ul>

        <label
          className="mt-7 flex cursor-pointer items-start gap-3 border p-4 text-sm"
          style={{ borderColor: agreed ? "#0f172a" : "#e2e8f0", color: "#0f172a" }}
        >
          <input
            type="checkbox"
            checked={agreed}
            onChange={(e) => setAgreed(e.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer"
          />
          <span>
            I agree to the{" "}
            <a
              href={`${SITE}/terms`}
              target="_blank"
              rel="noopener noreferrer"
              className={link}
            >
              Terms of Use
            </a>{" "}
            and the{" "}
            <a
              href={`${SITE}/privacy`}
              target="_blank"
              rel="noopener noreferrer"
              className={link}
            >
              Privacy Policy
            </a>
            .
          </span>
        </label>

        {accept.isError && (
          <p className="mt-3 text-sm" style={{ color: "#dc2626" }}>
            {accept.error instanceof Error
              ? accept.error.message
              : "Could not record your acceptance. Please try again."}
          </p>
        )}

        <Button
          className="mt-6 w-full"
          disabled={!agreed || !data || accept.isPending}
          onClick={() =>
            data &&
            accept.mutate(data.current_version, {
              onSuccess: () => router.replace(home),
            })
          }
        >
          {accept.isPending ? "One moment…" : "Agree and continue"}
        </Button>

        <p className="mt-4 text-xs" style={{ color: "#94a3b8" }}>
          Version {data?.current_version ?? "\u2026"}. You can read both documents again
          any time from Settings.
        </p>
      </div>
    </AuthShell>
  );
}
