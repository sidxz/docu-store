"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@docu-store/api-client";
import { queryKeys } from "@/lib/query-keys";

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
      return data;
    },
    enabled: !!pageId,
    refetchInterval: (query) => {
      const result = query.state.data as
        | { workflows?: Record<string, { status?: string }> }
        | undefined;
      const workflows = result?.workflows;
      const hasRunning = workflows
        ? Object.values(workflows).some((w) => w.status === "RUNNING")
        : false;
      return hasRunning ? 3000 : false;
    },
  });
}
