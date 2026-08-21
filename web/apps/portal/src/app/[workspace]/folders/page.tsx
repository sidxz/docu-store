"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Folder as FolderIcon, MessageSquare } from "lucide-react";
import { FolderStrip } from "@/components/folders/FolderStrip";
import { ChatRow } from "@/components/folders/ChatRow";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useFolders, useFolderChats } from "@/hooks/use-folders";

export default function FoldersPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const { data: folders } = useFolders();
  const selectedFolder = folders?.find((f) => f.folder_id === selectedFolderId);
  const {
    data: chatsData,
    isLoading,
    hasNextPage,
    fetchNextPage,
    isFetchingNextPage,
  } = useFolderChats(selectedFolderId ?? undefined);
  const chats = chatsData?.pages.flat();

  // Deselect a folder that no longer exists (e.g. deleted while open).
  useEffect(() => {
    if (folders !== undefined && selectedFolderId !== null && !selectedFolder) {
      setSelectedFolderId(null);
    }
  }, [folders, selectedFolderId, selectedFolder]);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-text-primary">Folders</h1>
        <p className="mt-1 text-sm text-text-muted">
          Organize your research sessions. Drag one onto a folder, or open a folder to see what is inside.
        </p>
      </div>

      <FolderStrip selectedFolderId={selectedFolderId} onSelect={setSelectedFolderId} />

      {!selectedFolderId ? (
        // Don't flash "No folders yet" while the folder list is still loading.
        folders === undefined ? null : (
          <div className="flex flex-col items-center rounded-xl border border-dashed border-border-default bg-surface-elevated py-16 text-center">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-accent-light">
              <FolderIcon className="h-6 w-6 text-feature-folder" />
            </div>
            <p className="text-sm font-medium text-text-primary">
              {folders.length ? "Select a folder" : "No folders yet"}
            </p>
            <p className="mt-1 max-w-sm text-xs text-text-muted">
              {folders.length
                ? "Click a folder above to see its research sessions."
                : "Create a folder, then drag chats into it from the dashboard or the ⋯ menu on a chat."}
            </p>
          </div>
        )
      ) : isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-lg border border-border-default bg-surface-elevated p-4">
              <Skeleton className="h-4 w-1/2" />
            </div>
          ))}
        </div>
      ) : !chats?.length ? (
        <div className="flex flex-col items-center rounded-xl border border-dashed border-border-default bg-surface-elevated py-16 text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-accent-light">
            <MessageSquare className="h-6 w-6 text-accent-text" />
          </div>
          <p className="text-sm font-medium text-text-primary">
            {selectedFolder?.name} is empty
          </p>
          <p className="mt-1 max-w-sm text-xs text-text-muted">
            Drag a research session onto this folder, or use the ⋯ menu on one to move it here.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {chats.map((chat) => (
            <ChatRow key={chat.conversation_id} chat={chat} workspace={workspace} />
          ))}
          {hasNextPage && (
            <Button
              variant="ghost"
              size="sm"
              className="w-full"
              onClick={() => fetchNextPage()}
              disabled={isFetchingNextPage}
            >
              {isFetchingNextPage ? "Loading…" : "Load more"}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
