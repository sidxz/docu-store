"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { authFetch, authFetchJson } from "@/lib/auth-fetch";
import { queryKeys } from "@/lib/query-keys";
import type { ChatFolder, Conversation } from "@docu-store/types";

const FOLDER_CHATS_PAGE_SIZE = 100;

// ── Queries ─────────────────────────────────────────────────────────────────

export function useFolders() {
  return useQuery({
    queryKey: queryKeys.chat.folders(),
    queryFn: () => authFetchJson<ChatFolder[]>("/folders"),
    staleTime: 30_000,
  });
}

export function useFolderChats(folderId: string | undefined) {
  return useInfiniteQuery({
    queryKey: queryKeys.chat.folderChats(folderId ?? ""),
    queryFn: ({ pageParam }) =>
      authFetchJson<Conversation[]>(
        `/chat?folder_id=${folderId}&skip=${pageParam}&limit=${FOLDER_CHATS_PAGE_SIZE}`,
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) =>
      lastPage.length === FOLDER_CHATS_PAGE_SIZE
        ? allPages.length * FOLDER_CHATS_PAGE_SIZE
        : undefined,
    enabled: !!folderId,
    staleTime: 30_000,
  });
}

// ── Mutations ────────────────────────────────────────────────────────────────

/**
 * The deleted/moved chats' folder_id changed, so refresh the conversation
 * list and the dashboard's recent panel — but NOT the whole chat namespace
 * (chat.all would also refetch transcripts and the expensive /chat/usage
 * aggregation). `recent` is parameterized by limit, so invalidate by prefix.
 */
function invalidateChatLists(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: queryKeys.chat.list() });
  queryClient.invalidateQueries({ queryKey: [...queryKeys.chat.all, "recent"] });
}

export function useCreateFolder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      authFetchJson<ChatFolder>("/folders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.chat.folders() });
    },
  });
}

export function useRenameFolder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ folderId, name }: { folderId: string; name: string }) =>
      authFetchJson<ChatFolder>(`/folders/${folderId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.chat.folders() });
    },
  });
}

export function useDeleteFolder() {
  const queryClient = useQueryClient();
  return useMutation({
    // Hand-rolled (not authFetchJson): 204 has no JSON body, and 404 is
    // tolerated — the folder is already gone.
    mutationFn: async (folderId: string) => {
      const res = await authFetch(`/folders/${folderId}`, { method: "DELETE" });
      if (!res.ok && res.status !== 404) throw new Error("Failed to delete folder");
    },
    onSuccess: (_data, folderId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.chat.folders() });
      queryClient.invalidateQueries({
        queryKey: queryKeys.chat.folderChats(folderId),
      });
      invalidateChatLists(queryClient);
    },
  });
}

/**
 * Move a chat into a folder (toFolderId=null removes it). Optimistically
 * adjusts folder counts on the tiles so a drag-drop feels instant.
 */
export function useSetChatFolder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      conversationId,
      toFolderId,
    }: {
      conversationId: string;
      toFolderId: string | null;
      fromFolderId?: string | null;
    }) =>
      authFetchJson<Conversation>(`/chat/${conversationId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder_id: toFolderId }),
      }),
    onMutate: async ({ toFolderId, fromFolderId }) => {
      if (toFolderId === fromFolderId) return { prev: undefined };
      await queryClient.cancelQueries({ queryKey: queryKeys.chat.folders() });
      const prev = queryClient.getQueryData<ChatFolder[]>(queryKeys.chat.folders());
      if (prev) {
        const now = new Date().toISOString();
        queryClient.setQueryData<ChatFolder[]>(
          queryKeys.chat.folders(),
          prev.map((f) => {
            if (f.folder_id === toFolderId)
              return { ...f, chat_count: f.chat_count + 1, updated_at: now };
            if (f.folder_id === fromFolderId)
              return { ...f, chat_count: Math.max(0, f.chat_count - 1), updated_at: now };
            return f;
          }),
        );
      }
      return { prev };
    },
    onSuccess: (data, vars) => {
      // Merge the new folder_id into the cached detail (which also holds the
      // messages) instead of invalidating — no need to refetch the transcript.
      queryClient.setQueryData<Conversation>(
        queryKeys.chat.detail(vars.conversationId),
        (old) => (old ? { ...old, folder_id: data.folder_id } : old),
      );
    },
    onError: (_err, _vars, context) => {
      if (context?.prev) {
        queryClient.setQueryData(queryKeys.chat.folders(), context.prev);
      }
    },
    onSettled: (_data, _err, vars) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.chat.folders() });
      invalidateChatLists(queryClient);
      if (vars.fromFolderId) {
        queryClient.invalidateQueries({
          queryKey: queryKeys.chat.folderChats(vars.fromFolderId),
        });
      }
      if (vars.toFolderId) {
        queryClient.invalidateQueries({
          queryKey: queryKeys.chat.folderChats(vars.toFolderId),
        });
      }
    },
  });
}
