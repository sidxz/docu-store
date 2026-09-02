"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, MessageSquare, ChevronLeft } from "lucide-react";
import { conversationHref } from "@/lib/surfaces";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecentChats, useCreateConversation } from "@/hooks/use-chat";
import { useFolders, useFolderChats } from "@/hooks/use-folders";
import { FolderStrip } from "@/components/folders/FolderStrip";
import { ChatRow } from "@/components/folders/ChatRow";
import { RecentChatCard } from "./RecentChatCard";

export function RecentChatsPanel({ workspace }: { workspace: string }) {
  const router = useRouter();
  const { data: chats, isLoading } = useRecentChats(5);
  const createConversation = useCreateConversation();

  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const { data: folders } = useFolders();
  const selectedFolder = folders?.find((f) => f.folder_id === selectedFolderId);
  const {
    data: folderChatsData,
    isLoading: folderLoading,
    hasNextPage,
    fetchNextPage,
    isFetchingNextPage,
  } = useFolderChats(selectedFolderId ?? undefined);
  const folderChats = folderChatsData?.pages.flat();

  // Deselect a folder that no longer exists (e.g. deleted while open).
  useEffect(() => {
    if (folders !== undefined && selectedFolderId !== null && !selectedFolder) {
      setSelectedFolderId(null);
    }
  }, [folders, selectedFolderId, selectedFolder]);

  const handleNew = async () => {
    const conv = await createConversation.mutateAsync(undefined);
    // Research by default (useCreateConversation() takes no surface here);
    // routed through the helper so the URL follows if that ever changes.
    router.push(conversationHref(workspace, "research", conv.conversation_id));
  };

  const inFolder = selectedFolderId !== null;

  return (
    <>
      {/* My Chats — folders */}
      <section className="mb-6">
        <h2 className="mb-3 text-sm font-semibold text-text-primary">My Folders</h2>
        <FolderStrip selectedFolderId={selectedFolderId} onSelect={setSelectedFolderId} />
        {folders?.length === 0 && (
          <p className="text-xs text-text-muted">
            No folders yet — create one and drag research sessions into it to organize them.
          </p>
        )}
      </section>

      {/* Recent — or the selected folder's chats */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          {inFolder ? (
            <button
              type="button"
              onClick={() => setSelectedFolderId(null)}
              className="flex min-w-0 items-center gap-1 text-sm font-semibold text-text-primary transition-colors hover:text-accent-text"
            >
              <ChevronLeft className="size-4 shrink-0" />
              <span className="truncate">{selectedFolder?.name ?? "Folder"}</span>
            </button>
          ) : (
            <h2 className="text-sm font-semibold text-text-primary">Recent Research</h2>
          )}
          <Button size="sm" onClick={handleNew} disabled={createConversation.isPending}>
            <Plus className="size-4" />
            New Research
          </Button>
        </div>

        {inFolder ? (
          folderLoading ? (
            <ListSkeleton />
          ) : !folderChats?.length ? (
            <Empty
              title="This folder is empty"
              hint="Drag a research session here, or use its ⋯ menu to move it into this folder."
            />
          ) : (
            <div className="space-y-2">
              {folderChats.map((chat) => (
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
          )
        ) : isLoading ? (
          <ListSkeleton />
        ) : !chats?.length ? (
          <div className="flex flex-col items-center rounded-xl border border-border-default bg-surface-elevated py-10 text-center">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-accent-light">
              <MessageSquare className="h-6 w-6 text-accent-text" />
            </div>
            <p className="text-sm font-medium text-text-primary">No research sessions yet</p>
            <p className="mt-1 text-xs text-text-muted">
              Start your first research session to explore your documents.
            </p>
            <Button size="sm" className="mt-4" onClick={handleNew} disabled={createConversation.isPending}>
              <Plus className="size-4" />
              New Research
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {chats.map((chat) => (
              <RecentChatCard key={chat.conversation_id} chat={chat} workspace={workspace} />
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="rounded-xl border border-border-default bg-surface-elevated p-4">
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="mt-2 h-3 w-3/4" />
        </div>
      ))}
    </div>
  );
}

function Empty({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-border-default bg-surface-elevated py-10 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-accent-light">
        <MessageSquare className="h-6 w-6 text-accent-text" />
      </div>
      <p className="text-sm font-medium text-text-primary">{title}</p>
      <p className="mt-1 max-w-xs text-xs text-text-muted">{hint}</p>
    </div>
  );
}
