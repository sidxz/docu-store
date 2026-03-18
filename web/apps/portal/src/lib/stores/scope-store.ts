import { create } from "zustand";
import { persist } from "zustand/middleware";

type Scope = "workspace" | "private";

interface ScopeState {
  defaultScope: Scope;
  setDefaultScope: (scope: Scope) => void;
}

export const useScopeStore = create<ScopeState>()(
  persist(
    (set) => ({
      defaultScope: "workspace",
      setDefaultScope: (scope) => set({ defaultScope: scope }),
    }),
    { name: "ds-default-scope" },
  ),
);
