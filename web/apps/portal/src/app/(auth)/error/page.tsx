import { AlertTriangle } from "lucide-react";

export default function AuthErrorPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-sunken">
      <div className="w-full max-w-sm rounded-xl border border-border-default bg-surface-elevated p-8 text-center shadow-ds">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-ds-error/10">
          <AlertTriangle className="h-6 w-6 text-ds-error" />
        </div>
        <h1 className="text-xl font-semibold text-text-primary">
          Authentication Error
        </h1>
        <p className="mt-2 text-sm text-text-secondary">
          Something went wrong during sign-in. Please try again.
        </p>
      </div>
    </div>
  );
}
