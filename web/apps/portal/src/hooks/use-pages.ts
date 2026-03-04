"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@docu-store/api-client";
import { queryKeys } from "@/lib/query-keys";

/** Shape of the workflow endpoint response (untyped in OpenAPI schema) */
interface WorkflowMap {
  workflows?: Record<string, { workflow_id: string; status: string }>;
}

export function usePage(pageId: string) {
  return useQuery({
    queryKey: queryKeys.pages.detail(pageId),
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/pages/{page_id}", {
        params: { path: { page_id: pageId } },
      });
      if (error) throw new Error("Failed to fetch page");
      return data;
    },
    enabled: !!pageId,
  });
}

export function usePageWorkflows(pageId: string) {
  return useQuery({
    queryKey: queryKeys.pages.workflows(pageId),
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/pages/{page_id}/workflows",
        { params: { path: { page_id: pageId } } },
      );
      if (error) throw new Error("Failed to fetch page workflows");
      return data as WorkflowMap;
    },
    enabled: !!pageId,
    // Poll every 3 s while any workflow is RUNNING; same strategy as useArtifactWorkflows.
    refetchInterval: (query) => {
      const workflows = (query.state.data as WorkflowMap | undefined)?.workflows;
      const hasRunning = workflows
        ? Object.values(workflows).some((w) => w.status === "RUNNING")
        : false;
      return hasRunning ? 3000 : false;
    },
  });
}
