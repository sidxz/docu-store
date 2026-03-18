"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@docu-store/api-client";
import type { ResourceACL } from "@docu-store/types";
import { queryKeys } from "@/lib/query-keys";

export function useArtifactPermissions(artifactId: string) {
  return useQuery({
    queryKey: queryKeys.artifacts.permissions(artifactId),
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/artifacts/{artifact_id}/permissions",
        { params: { path: { artifact_id: artifactId } } },
      );
      if (error) throw new Error("Failed to fetch permissions");
      return data as unknown as ResourceACL;
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
      share: { grantee_type: string; grantee_id: string; permission: string };
    }) => {
      const { data, error } = await apiClient.POST(
        "/artifacts/{artifact_id}/shares",
        {
          params: { path: { artifact_id: artifactId } },
          body: share,
        },
      );
      if (error) throw new Error("Failed to share artifact");
      return data;
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
      share: { grantee_type: string; grantee_id: string; permission: string };
    }) => {
      const { data, error } = await apiClient.DELETE(
        "/artifacts/{artifact_id}/shares",
        {
          params: { path: { artifact_id: artifactId } },
          body: share,
        },
      );
      if (error) throw new Error("Failed to revoke share");
      return data;
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
      visibility: string;
    }) => {
      const { data, error } = await apiClient.PATCH(
        "/artifacts/{artifact_id}/visibility",
        {
          params: { path: { artifact_id: artifactId } },
          body: { visibility },
        },
      );
      if (error) throw new Error("Failed to update visibility");
      return data;
    },
    onSuccess: (_, { artifactId }) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.artifacts.permissions(artifactId),
      });
    },
  });
}
