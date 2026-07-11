"use client";

import { useQuery } from "@tanstack/react-query";
import type { Bioactivity } from "@docu-store/types";
import { authFetch } from "@/lib/auth-fetch";
import { queryKeys } from "@/lib/query-keys";

export interface CompoundPageRef {
  page_id: string;
  page_index: number;
  artifact_id: string;
  artifact_title: string | null;
}

export interface CompoundProfile {
  name: string;
  extracted_id: string | null;
  canonical_smiles: string | null;
  has_structure: boolean;
  synonyms: string[];
  bioactivities: Bioactivity[];
  reference_pages: CompoundPageRef[];
}

export function useCompoundProfile(name: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.compounds.detail(name ?? ""),
    queryFn: async (): Promise<CompoundProfile> => {
      const res = await authFetch(`/compounds/${encodeURIComponent(name!)}/profile`);
      if (!res.ok) throw new Error(`Compound profile failed: ${res.status}`);
      return (await res.json()) as CompoundProfile;
    },
    enabled: !!name,
    staleTime: 5 * 60 * 1000,
  });
}
