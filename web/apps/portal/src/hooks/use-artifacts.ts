"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@docu-store/api-client";
import { queryKeys } from "@/lib/query-keys";

/** Shape of the workflow endpoint response (untyped in OpenAPI schema) */
interface WorkflowMap {
  workflows?: Record<string, { workflow_id: string; status: string }>;
}

export function useArtifacts(skip = 0, limit = 50) {
  return useQuery({
    queryKey: [...queryKeys.artifacts.list(), { skip, limit }],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/artifacts", {
        params: { query: { skip, limit } },
      });
      if (error) throw new Error("Failed to fetch artifacts");
      return data;
    },
  });
}

export function useArtifact(id: string) {
  return useQuery({
    queryKey: queryKeys.artifacts.detail(id),
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/artifacts/{artifact_id}",
        { params: { path: { artifact_id: id } } },
      );
      if (error) throw new Error("Failed to fetch artifact");
      return data;
    },
    enabled: !!id,
  });
}

export function useArtifactWorkflows(id: string) {
  return useQuery({
    queryKey: queryKeys.artifacts.workflows(id),
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/artifacts/{artifact_id}/workflows",
        { params: { path: { artifact_id: id } } },
      );
      if (error) throw new Error("Failed to fetch workflows");
      return data as WorkflowMap;
    },
    enabled: !!id,
    // Poll every 3 s while any workflow is RUNNING; stop once all settle.
    // The backend proxies to Temporal, so this drives real-time status updates.
    refetchInterval: (query) => {
      const workflows = (query.state.data as WorkflowMap | undefined)?.workflows;
      const hasRunning = workflows
        ? Object.values(workflows).some((w) => w.status === "RUNNING")
        : false;
      return hasRunning ? 3000 : false;
    },
  });
}

export function useArtifactSummary(id: string) {
  return useQuery({
    queryKey: queryKeys.artifacts.summary(id),
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/artifacts/{artifact_id}/summary",
        { params: { path: { artifact_id: id } } },
      );
      if (error) throw new Error("Failed to fetch summary");
      return data;
    },
    enabled: !!id,
  });
}

export function useUploadArtifact() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      file,
      artifactType,
      sourceUri,
    }: {
      file: File;
      artifactType: string;
      sourceUri?: string;
    }) => {
      // apiClient doesn't support multipart/form-data, so use fetch directly.
      // Base URL is shared with apiClient via the same env var.
      const baseUrl =
        process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const formData = new FormData();
      formData.append("file", file);
      formData.append("artifact_type", artifactType);
      if (sourceUri) formData.append("source_uri", sourceUri);

      const res = await fetch(`${baseUrl}/artifacts/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errorBody = await res.text();
        throw new Error(`Upload failed: ${res.status} ${errorBody}`);
      }

      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.artifacts.all });
    },
  });
}

export function useDeleteArtifact() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await apiClient.DELETE(
        "/artifacts/{artifact_id}",
        { params: { path: { artifact_id: id } } },
      );
      if (error) throw new Error("Failed to delete artifact");
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.artifacts.all });
    },
  });
}
