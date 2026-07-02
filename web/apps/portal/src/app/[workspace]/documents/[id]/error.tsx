"use client";

import { AlertTriangle, ArrowLeft, RefreshCw } from "lucide-react";
import { useParams, useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";

export default function DocumentError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { workspace } = useParams<{ workspace: string }>();
  const router = useRouter();

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-ds-error/10">
        <AlertTriangle className="h-6 w-6 text-ds-error" />
      </div>
      <h2 className="text-lg font-semibold text-text-primary">
        Failed to load document
      </h2>
      <p className="mt-2 max-w-md text-sm text-text-secondary">
        This document may not exist or the backend is unreachable.
      </p>
      {process.env.NODE_ENV === "development" && (
        <pre className="mt-4 max-w-lg overflow-auto rounded-lg border border-border-default bg-surface-sunken p-3 text-left text-xs text-ds-error">
          {error.message}
        </pre>
      )}
      <div className="mt-6 flex items-center gap-3">
        <Button
          onClick={() => router.push(`/${workspace}/documents`)}
          variant="ghost"
        >
          <ArrowLeft className="size-4" />
          Back to Documents
        </Button>
        <Button onClick={reset} variant="outline">
          <RefreshCw className="size-4" />
          Try again
        </Button>
      </div>
    </div>
  );
}
