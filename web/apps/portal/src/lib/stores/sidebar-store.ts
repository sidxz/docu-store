import { create } from "zustand";
import { persist } from "zustand/middleware";

// Persisted so the sidebar stays collapsed/expanded across page navigations
// and browser sessions without a server round-trip.

interface SidebarState {
  collapsed: boolean;
  toggleCollapsed: () => void;
  setCollapsed: (collapsed: boolean) => void;
}

export const useSidebarStore = create<SidebarState>()(
  persist(
    (set) => ({
      collapsed: false,
      toggleCollapsed: () =>
        set((state) => ({ collapsed: !state.collapsed })),
      setCollapsed: (collapsed) => set({ collapsed }),
    }),
    {
      name: "ds-sidebar",
    },
  ),
);
