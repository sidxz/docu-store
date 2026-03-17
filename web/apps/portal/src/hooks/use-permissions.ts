"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ResourceACL, ShareRequest } from "@docu-store/types";
import { queryKeys } from "@/lib/query-keys";
import { getAuthzClient } from "@/lib/authz-client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Authenticated fetch helper. The new permission endpoints are not yet in the
 * generated OpenAPI schema, so we use raw fetch with Sentinel auth headers
 * until the schema is regenerated.
 */
async function authFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = {
    ...getAuthzClient().getHeaders(),
    "Content-Type": "application/json",
    ...init?.headers,
  };
  return fetch(`${API_URL}${path}`, { ...init, headers });
}

export function useArtifactPermissions(artifactId: string) {
  return useQuery({
    queryKey: queryKeys.artifacts.permissions(artifactId),
    queryFn: async () => {
      const res = await authFetch(`/artifacts/${artifactId}/permissions`);
      if (!res.ok) throw new Error("Failed to fetch permissions");
      return (await res.json()) as ResourceACL;
    },
    enabled: !!artifactId,
  });
}

export function useShareArtifact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      artifactId,
      share,
    }: {
      artifactId: string;
      share: ShareRequest;
    }) => {
      const res = await authFetch(`/artifacts/${artifactId}/shares`, {
        method: "POST",
        body: JSON.stringify(share),
      });
      if (!res.ok) throw new Error("Failed to share artifact");
      return res.json();
    },
    onSuccess: (_, { artifactId }) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.artifacts.permissions(artifactId),
      });
    },
  });
}

export function useRevokeShare() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      artifactId,
      share,
    }: {
      artifactId: string;
      share: ShareRequest;
    }) => {
      const res = await authFetch(`/artifacts/${artifactId}/shares`, {
        method: "DELETE",
        body: JSON.stringify(share),
      });
      if (!res.ok) throw new Error("Failed to revoke share");
      return res.json();
    },
    onSuccess: (_, { artifactId }) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.artifacts.permissions(artifactId),
      });
    },
  });
}

export function useUpdateVisibility() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      artifactId,
      visibility,
    }: {
      artifactId: string;
      visibility: "private" | "workspace";
    }) => {
      const res = await authFetch(`/artifacts/${artifactId}/visibility`, {
        method: "PATCH",
        body: JSON.stringify({ visibility }),
      });
      if (!res.ok) throw new Error("Failed to update visibility");
      return res.json();
    },
    onSuccess: (_, { artifactId }) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.artifacts.permissions(artifactId),
      });
    },
  });
}
