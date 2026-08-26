import type { ReactNode } from "react";

import { ShapeGrid } from "@/components/backgrounds/ShapeGrid";

/** Full-screen, light-only shell shared by the auth callback and onboarding pages. */
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="fixed inset-0 overflow-hidden" style={{ background: "#f6f8fb" }}>
      <ShapeGrid />
      <div className="relative z-10 flex min-h-screen items-center justify-center px-4">
        {children}
      </div>
    </div>
  );
}
