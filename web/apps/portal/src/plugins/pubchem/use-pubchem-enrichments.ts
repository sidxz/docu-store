"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query-keys";
import { getAuthzClient } from "@/lib/authz-client";
import { API_URL } from "@/lib/constants";
import type { PubChemEnrichment } from "./types";

export function usePubChemEnrichments(
  pageId: string,
  { enabled = true }: { enabled?: boolean } = {},
) {
  const { data: enrichments } = useQuery<PubChemEnrichment[]>({
    queryKey: queryKeys.plugins.enrichments("pubchem", pageId),
    queryFn: async () => {
      const headers = getAuthzClient().getHeaders();
      const res = await fetch(
        `${API_URL}/plugins/pubchem/pages/${pageId}/enrichments`,
        { headers },
      );
      if (!res.ok) return [];
      return res.json();
    },
    enabled: enabled && !!pageId,
  });

  const enrichmentBySmiles = useMemo(() => {
    if (!enrichments) return undefined;
    const map = new Map<string, PubChemEnrichment>();
    for (const e of enrichments) {
      map.set(e.canonical_smiles, e);
    }
    return map;
  }, [enrichments]);

  return { enrichments, enrichmentBySmiles };
}
