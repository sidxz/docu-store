"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { authFetchJson } from "@/lib/auth-fetch";
import { queryKeys } from "@/lib/query-keys";

/** GET /workspace/storage. Bytes throughout; null limits mean "not set". */
export interface WorkspaceStorage {
  /** What the limit counts: the uploaded files. */
  uploaded_bytes: number;
  /** Everything stored for the workspace, page images included; null if unmeasured. */
  on_disk_bytes: number | null;
  /** The admin's own limit. */
  limit_bytes: number | null;
  /** The deployment cap no workspace can exceed. */
  cap_bytes: number | null;
  /** The lower of the two — what uploads are checked against. */
  effective_limit_bytes: number | null;
}

export function useWorkspaceStorage() {
  return useQuery({
    queryKey: queryKeys.workspace.storage(),
    queryFn: () => authFetchJson<WorkspaceStorage>("/workspace/storage"),
  });
}

export function useSetStorageLimit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (limitBytes: number | null) =>
      authFetchJson<void>("/workspace/storage/limit", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit_bytes: limitBytes }),
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.workspace.storage() }),
  });
}
