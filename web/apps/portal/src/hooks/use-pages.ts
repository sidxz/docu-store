"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@docu-store/api-client";
import type { WorkflowMap } from "@docu-store/types";
import { queryKeys, workflowPollingInterval } from "@/lib/query-keys";
import { throwApiError } from "@/lib/api-error";

export function usePage(pageId: string) {
  return useQuery({
    queryKey: queryKeys.pages.detail(pageId),
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET("/pages/{page_id}", {
        params: { path: { page_id: pageId } },
      });
      if (error) throwApiError("Failed to fetch page", error, response.status);

      if (process.env.NODE_ENV === "development") {
        console.groupCollapsed(
          `[docu-store] Page data · ${pageId.slice(0, 8)}…`,
        );
        const d = data as Record<string, unknown> | undefined;
        if (d?.tag_mentions) {
          console.log("tag_mentions:", d.tag_mentions);
        }
        if (d?.compound_mentions) {
          console.log("compound_mentions:", d.compound_mentions);
        }
        if (d?.summary_candidate) {
          console.log("summary_candidate:", d.summary_candidate);
        }
        if (d?.text_mention) {
          const tm = d.text_mention as Record<string, unknown>;
          console.log("text_mention:", {
            model_name: tm.model_name,
            confidence: tm.confidence,
            text_length: typeof tm.text === "string" ? tm.text.length : 0,
          });
        }
        console.groupEnd();
      }

      return data;
    },
    enabled: !!pageId,
  });
}

/** Page workflow keys (from backend) that have rerun API endpoints. */
export const RERUNNABLE_PAGE_WORKFLOWS = new Set([
  "embedding",
  "compound_extraction",
  "smiles_embedding",
  "page_summarization",
  "ner_extraction",
]);

export function usePageWorkflows(pageId: string) {
  return useQuery({
    queryKey: queryKeys.pages.workflows(pageId),
    queryFn: async () => {
      const { data, error, response } = await apiClient.GET(
        "/pages/{page_id}/workflows",
        { params: { path: { page_id: pageId } } },
      );
      if (error) throwApiError("Failed to fetch page workflows", error, response.status);
      const result = data as WorkflowMap;

      if (process.env.NODE_ENV === "development" && result?.workflows) {
        console.groupCollapsed(
          `[docu-store] Page workflows · ${pageId.slice(0, 8)}…`,
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
    enabled: !!pageId,
    refetchInterval: workflowPollingInterval,
  });
}

export interface CorrectedCompoundInput {
  smiles: string;
  extracted_id?: string | null;
  internal_id?: string | null;
  cdd_id?: string | null;
  chembl_id?: string | null;
  pdb_id?: string | null;
}

/** hiledit: full-replace correction of a page's compound mentions, with provenance recorded server-side. */
export function useCorrectPageCompounds(pageId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { compound_mentions: CorrectedCompoundInput[] }) => {
      const { data, error, response } = await apiClient.PUT(
        "/pages/{page_id}/compound_mentions",
        { params: { path: { page_id: pageId } }, body },
      );
      if (error) throwApiError("Failed to save corrections", error, response.status);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pages.detail(pageId) });
    },
  });
}

export function useRerunPageWorkflow(pageId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (workflowName: string) => {
      if (process.env.NODE_ENV === "development") {
        console.log(
          `[docu-store] ▶ Rerunning ${workflowName} · page ${pageId.slice(0, 8)}…`,
        );
      }

      let data: unknown;
      let error: unknown;

      switch (workflowName) {
        case "embedding":
          ({ data, error } = await apiClient.POST(
            "/pages/{page_id}/embeddings/generate",
            { params: { path: { page_id: pageId } } },
          ));
          break;
        case "compound_extraction":
          ({ data, error } = await apiClient.POST(
            "/pages/{page_id}/compounds/extract",
            { params: { path: { page_id: pageId } } },
          ));
          break;
        case "smiles_embedding":
          ({ data, error } = await apiClient.POST(
            "/pages/{page_id}/compounds/embed",
            { params: { path: { page_id: pageId } } },
          ));
          break;
        case "page_summarization":
          ({ data, error } = await apiClient.POST(
            "/pages/{page_id}/summarize",
            { params: { path: { page_id: pageId } } },
          ));
          break;
        case "ner_extraction":
          ({ data, error } = await apiClient.POST(
            "/pages/{page_id}/ner/extract",
            { params: { path: { page_id: pageId } } },
          ));
          break;
        default:
          throw new Error(`No rerun endpoint for workflow: ${workflowName}`);
      }

      if (error) throwApiError(`Failed to rerun ${workflowName}`, error);

      if (process.env.NODE_ENV === "development") {
        console.log(
          `[docu-store] ✓ ${workflowName} rerun accepted:`,
          data,
        );
      }

      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.pages.workflows(pageId),
      });
    },
  });
}
