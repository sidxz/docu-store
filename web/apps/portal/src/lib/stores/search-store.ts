import { create } from "zustand";

interface SearchState {
  /** Query to auto-execute on the search page. Set by SearchCommand, consumed once by the search page. */
  pendingQuery: string | null;
  setPendingQuery: (q: string | null) => void;
}

export const useSearchStore = create<SearchState>()((set) => ({
  pendingQuery: null,
  setPendingQuery: (q) => set({ pendingQuery: q }),
}));
