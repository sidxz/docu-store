"use client";

import { AuthzGuard } from "@sentinel-auth/react";
import { ProgressSpinner } from "primereact/progressspinner";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

function RedirectToLogin() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/login");
  }, [router]);
  return null;
}

export function AuthGuardWrapper({ children }: { children: ReactNode }) {
  return (
    <AuthzGuard
      fallback={<RedirectToLogin />}
      loading={
        <div className="flex h-screen items-center justify-center bg-surface-sunken">
          <ProgressSpinner
            style={{ width: "2rem", height: "2rem" }}
            strokeWidth="3"
          />
        </div>
      }
    >
      {children}
    </AuthzGuard>
  );
}
