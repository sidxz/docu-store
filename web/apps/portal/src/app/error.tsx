"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-ds-error/10">
        <AlertTriangle className="h-6 w-6 text-ds-error" />
      </div>
      <h2 className="text-lg font-semibold text-text-primary">
        Something went wrong
      </h2>
      <p className="mt-2 max-w-md text-sm text-text-secondary">
        An unexpected error occurred. Please try again or contact support if the
        problem persists.
      </p>
      {process.env.NODE_ENV === "development" && (
        <pre className="mt-4 max-w-lg overflow-auto rounded-lg border border-border-default bg-surface-sunken p-3 text-left text-xs text-ds-error">
          {error.message}
        </pre>
      )}
      <Button onClick={reset} className="mt-6" variant="outline">
        <RefreshCw className="size-4" />
        Try again
      </Button>
    </div>
  );
}
