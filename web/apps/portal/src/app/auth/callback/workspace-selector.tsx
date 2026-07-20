"use client";

import { useEffect, useRef, useState } from "react";
import type { AuthzWorkspaceSelectorProps } from "@sentinel-auth/react";

import { rememberWorkspace, rememberedWorkspace } from "@/lib/workspace-memory";

type Decision = { kind: "pending" } | { kind: "picker" } | { kind: "auto"; id: string };

export function WorkspaceSelector({
  workspaces,
  onSelect,
  isLoading,
}: AuthzWorkspaceSelectorProps) {
  const [decision, setDecision] = useState<Decision>({ kind: "pending" });
  // Dev StrictMode re-runs the mount effect before the decision state is visible;
  // the ref keeps the auto-select mint from firing twice.
  const autoFiredRef = useRef(false);

  // Skip the picker when the remembered workspace is still available — "Switch
  // workspace" in the topbar user menu forgets it and brings the picker back.
  // One-time decision made in an effect: localStorage is client-only, so a
  // useState initializer would cause a hydration mismatch.
  useEffect(() => {
    if (decision.kind !== "pending" || isLoading || autoFiredRef.current) return;
    const remembered = rememberedWorkspace();
    if (remembered && workspaces.some((ws) => ws.id === remembered)) {
      autoFiredRef.current = true;
      setDecision({ kind: "auto", id: remembered });
      onSelect(remembered);
    } else {
      setDecision({ kind: "picker" });
    }
  }, [decision.kind, isLoading, workspaces, onSelect]);

  if (decision.kind !== "picker") {
    const ws = decision.kind === "auto" ? workspaces.find((w) => w.id === decision.id) : null;
    return (
      <div className="text-center">
        <div className="mx-auto mb-3 h-6 w-6 animate-spin rounded-full border-2 border-[#e2e8f0] border-t-[#3b82f6]" />
        <p className="text-sm" style={{ color: "#64748b" }}>
          {ws ? `Entering ${ws.name}…` : "Signing you in…"}
        </p>
      </div>
    );
  }

  return (
    <div className="w-full max-w-sm">
      <h2
        className="mb-6 text-center text-lg font-semibold"
        style={{
          color: "#0f172a",
          animation: "auth-enter 0.6s ease-out 0.1s both",
        }}
      >
        Select Workspace
      </h2>
      <div className="space-y-2">
        {workspaces.map((ws, i) => (
          <button
            key={ws.id}
            onClick={() => {
              rememberWorkspace(ws.id);
              onSelect(ws.id);
            }}
            disabled={isLoading}
            className="w-full rounded-xl border border-[#e2e8f0] bg-white p-4 text-left transition-colors hover:border-[#3b82f6] hover:bg-[#f8fafc] disabled:opacity-50"
            style={{
              animation: `auth-enter 0.5s ease-out ${0.15 + i * 0.05}s both`,
            }}
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium" style={{ color: "#0f172a" }}>
                  {ws.name}
                </div>
                <div className="text-xs" style={{ color: "#64748b" }}>
                  {ws.slug}
                </div>
              </div>
              <span
                className="rounded-full px-2 py-0.5 text-xs font-medium"
                style={{ background: "#eff6ff", color: "#2563eb" }}
              >
                {ws.role}
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
