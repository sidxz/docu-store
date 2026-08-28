"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@docu-store/api-client";
import type { WorkflowMap } from "@docu-store/types";
import { queryKeys, workflowPollingInterval } from "@/lib/query-keys";
import { throwApiError } from "@/lib/api-error";
import { authFetchJson } from "@/lib/auth-fetch";

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
  structure_bbox?: number[] | null;
  label_bbox?: number[] | null;
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
    // Return the invalidations so mutateAsync awaits the refetch before the caller
    // closes the dialog / toasts. Also refresh the artifact detail — its embedded
    // pages feed the document Pages tab's per-page compound counts.
    onSuccess: (data) => {
      const artifactId = data?.artifact_id;
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.pages.detail(pageId) }),
        ...(artifactId
          ? [queryClient.invalidateQueries({ queryKey: queryKeys.artifacts.detail(artifactId) })]
          : []),
      ]);
    },
  });
}

/** Boxes in CSER-render pixels — the same space every stored bbox uses. Both null = warm-up. */
export interface AnalyzeBoxInput {
  structure_bbox: number[] | null;
  label_bbox: number[] | null;
}

/** What the models read out of those boxes: DECIMER for the structure, OCR for the label.
 *  Either can be null — DECIMER returns nothing for a crop it can't resolve. */
export interface AnalyzeBoxResult {
  smiles: string | null;
  label_text: string | null;
}

/**
 * hiledit: read a drawn box instead of asking a human to transcribe a scaffold by eye.
 *
 * Both boxes null is a deliberate warm-up call: it loads the model and returns nulls.
 * The first call in a server process pays ~94s for that load and every later one ~0.5s,
 * so firing one when the reviewer enters edit mode is what makes the real Analyse feel
 * instant. 404 means the page has no stored CSER render.
 *
 * ponytail: `authFetchJson` rather than `apiClient` — this route is not in the generated
 * OpenAPI schema yet; move it to apiClient.POST after the backend ships and `pnpm generate`
 * runs. authFetchJson is the house wrapper for exactly that gap and refreshes + retries once
 * on 401, which matters most here: this is the longest-lived request in the app and the one
 * most likely to straddle a token boundary. No timeout is imposed anywhere in this client,
 * and none is wanted: a cold call legitimately runs ~95s.
 */
export function useAnalyzeBox(pageId: string) {
  return useMutation({
    mutationFn: (body: AnalyzeBoxInput) =>
      authFetchJson<AnalyzeBoxResult>(`/pages/${pageId}/compounds/analyze-box`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
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
