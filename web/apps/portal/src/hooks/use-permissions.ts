"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@docu-store/api-client";
import type { ResourceACL } from "@docu-store/types";
import { queryKeys } from "@/lib/query-keys";
import { throwApiError } from "@/lib/api-error";

export function useArtifactPermissions(artifactId: string) {
  return useQuery({
    queryKey: queryKeys.artifacts.permissions(artifactId),
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET(
        "/artifacts/{artifact_id}/permissions",
        { params: { path: { artifact_id: artifactId } } },
      );
      if (error) throwApiError("Failed to fetch permissions", error, response.status);
      // Schema type doesn't overlap with hand-typed ResourceACL — double cast needed
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
      const { data, error, response } = await apiClient.POST(
        "/artifacts/{artifact_id}/shares",
        {
          params: { path: { artifact_id: artifactId } },
          body: share,
        },
      );
      if (error) throwApiError("Failed to share artifact", error, response.status);
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
      const { data, error, response } = await apiClient.DELETE(
        "/artifacts/{artifact_id}/shares",
        {
          params: { path: { artifact_id: artifactId } },
          body: share,
        },
      );
      if (error) throwApiError("Failed to revoke share", error, response.status);
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
      const { data, error, response } = await apiClient.PATCH(
        "/artifacts/{artifact_id}/visibility",
        {
          params: { path: { artifact_id: artifactId } },
          body: { visibility },
        },
      );
      if (error) throwApiError("Failed to update visibility", error, response.status);
      return data;
    },
    onSuccess: (_, { artifactId }) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.artifacts.permissions(artifactId),
      });
    },
  });
}
