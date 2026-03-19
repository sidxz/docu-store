"use client";

import { useQuery } from "@tanstack/react-query";
import type {
  BrowseCategoriesResponse,
  BrowseFoldersResponse,
  ArtifactBrowseItemDTO,
} from "@docu-store/types";
import { queryKeys } from "@/lib/query-keys";
import { API_URL } from "@/lib/constants";
import { getAuthzClient } from "@/lib/authz-client";

async function browseFetch<T>(path: string): Promise<T> {
  const headers = getAuthzClient().getHeaders();
  const res = await fetch(`${API_URL}${path}`, { headers });
  if (!res.ok) throw new Error(`Browse fetch failed: ${res.status}`);
  return res.json();
}

export function useTagCategories() {
  return useQuery({
    queryKey: queryKeys.browse.categories(),
    queryFn: () => browseFetch<BrowseCategoriesResponse>("/browse/categories"),
    staleTime: 120_000,
  });
}

export function useTagFolders(entityType: string | null, parent?: string) {
  const params = parent ? `?parent=${encodeURIComponent(parent)}` : "";
  return useQuery({
    queryKey: queryKeys.browse.folders(entityType ?? "", parent),
    queryFn: () =>
      browseFetch<BrowseFoldersResponse>(
        `/browse/categories/${encodeURIComponent(entityType!)}/folders${params}`,
      ),
    enabled: !!entityType,
    staleTime: 60_000,
  });
}

export function useFolderArtifacts(
  entityType: string | null,
  tagValue: string | null,
) {
  return useQuery({
    queryKey: queryKeys.browse.artifacts(entityType ?? "", tagValue ?? ""),
    queryFn: () =>
      browseFetch<ArtifactBrowseItemDTO[]>(
        `/browse/categories/${encodeURIComponent(entityType!)}/folders/${encodeURIComponent(tagValue!)}/artifacts`,
      ),
    enabled: !!entityType && !!tagValue,
  });
}
