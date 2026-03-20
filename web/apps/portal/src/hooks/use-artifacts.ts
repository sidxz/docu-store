"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@docu-store/api-client";
import type { ArtifactResponse, WorkflowMap } from "@docu-store/types";
import { queryKeys } from "@/lib/query-keys";
import { getAuthzClient } from "@/lib/authz-client";
import { API_URL } from "@/lib/constants";
import { authFetch } from "@/lib/auth-fetch";
import { ApiError, throwApiError } from "@/lib/api-error";

export function useArtifacts(
  skip = 0,
  limit = 50,
  sort_by = "updated_at",
  sort_order: -1 | 1 = -1,
) {
  return useQuery({
    queryKey: [...queryKeys.artifacts.list(), { skip, limit, sort_by, sort_order }],
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET("/artifacts", {
        params: { query: { skip, limit, sort_by, sort_order } },
      });
      if (error) throwApiError("Failed to fetch artifacts", error, response.status);
      return data as ArtifactResponse[];
    },
  });
}

export function useArtifact(id: string) {
  return useQuery({
    queryKey: queryKeys.artifacts.detail(id),
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET(
        "/artifacts/{artifact_id}",
        { params: { path: { artifact_id: id } } },
      );
      if (error) throwApiError("Failed to fetch artifact", error, response.status);
      // The OpenAPI schema is missing author_mentions, presentation_date, compound_mentions
      // fields. The hand-typed ArtifactResponse includes them.
      return data as ArtifactResponse;
    },
    enabled: !!id,
  });
}

/** Artifact workflow keys (from backend) that have rerun API endpoints. */
export const RERUNNABLE_ARTIFACT_WORKFLOWS = new Set([
  "artifact_summarization",
  "doc_metadata_extraction",
]);

export function useArtifactWorkflows(id: string) {
  return useQuery({
    queryKey: queryKeys.artifacts.workflows(id),
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET(
        "/artifacts/{artifact_id}/workflows",
        { params: { path: { artifact_id: id } } },
      );
      if (error) throwApiError("Failed to fetch workflows", error, response.status);
      const result = data as WorkflowMap;

      if (process.env.NODE_ENV === "development" && result?.workflows) {
        console.groupCollapsed(
          `[docu-store] Artifact workflows · ${id.slice(0, 8)}…`,
        );
        console.table(
          Object.entries(result.workflows).map(([name, info]) => ({
            workflow: name,
            status: info.status,
            id: info.workflow_id,
          })),
        );
        console.groupEnd();
      }

      return result;
    },
    enabled: !!id,
    // Poll every 3 s while any workflow is RUNNING; stop once all settle.
    // The backend proxies to Temporal, so this drives real-time status updates.
    refetchInterval: (query) => {
      const workflows = (query.state.data as WorkflowMap | undefined)
        ?.workflows;
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
      const { data, error, response } = await apiClient.GET(
        "/artifacts/{artifact_id}/summary",
        { params: { path: { artifact_id: id } } },
      );
      if (error) throwApiError("Failed to fetch summary", error, response.status);
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
      visibility,
    }: {
      file: File;
      artifactType: string;
      sourceUri?: string;
      visibility?: "workspace" | "private";
    }) => {
      // apiClient doesn't support multipart/form-data, so use fetch directly.
      const formData = new FormData();
      formData.append("file", file);
      formData.append("artifact_type", artifactType);
      if (sourceUri) formData.append("source_uri", sourceUri);
      if (visibility) formData.append("visibility", visibility);

      const authHeaders = getAuthzClient().getHeaders();

      const res = await fetch(`${API_URL}/artifacts/upload`, {
        method: "POST",
        body: formData,
        headers: authHeaders,
      });

      if (!res.ok) {
        const errorBody = await res.text();
        throw new ApiError(`Upload failed: ${errorBody}`, res.status, errorBody);
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
      const { error, response } = await apiClient.DELETE(
        "/artifacts/{artifact_id}",
        { params: { path: { artifact_id: id } } },
      );
      if (error) throwApiError("Failed to delete artifact", error, response.status);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.artifacts.all });
    },
  });
}

export function useRerunArtifactWorkflow(artifactId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (workflowName: string) => {
      if (process.env.NODE_ENV === "development") {
        console.log(
          `[docu-store] ▶ Rerunning ${workflowName} · artifact ${artifactId.slice(0, 8)}…`,
        );
      }

      switch (workflowName) {
        case "artifact_summarization": {
          const { data, error, response } = await apiClient.POST(
            "/artifacts/{artifact_id}/summarize",
            { params: { path: { artifact_id: artifactId } } },
          );
          if (error) throwApiError(`Failed to rerun ${workflowName}`, error, response.status);

          if (process.env.NODE_ENV === "development") {
            console.log(
              `[docu-store] ✓ ${workflowName} rerun accepted:`,
              data,
            );
          }
          return data;
        }
        case "doc_metadata_extraction": {
          // Not in OpenAPI schema — use authFetch directly
          const res = await authFetch(
            `/artifacts/${artifactId}/extract-metadata`,
            { method: "POST" },
          );
          if (!res.ok) throw new ApiError(`Failed to rerun ${workflowName}`, res.status);
          const data = await res.json();

          if (process.env.NODE_ENV === "development") {
            console.log(
              `[docu-store] ✓ ${workflowName} rerun accepted:`,
              data,
            );
          }
          return data;
        }
        default:
          throw new Error(`No rerun endpoint for workflow: ${workflowName}`);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.artifacts.workflows(artifactId),
      });
    },
  });
}
