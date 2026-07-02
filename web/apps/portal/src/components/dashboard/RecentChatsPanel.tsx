"use client";

import { useRouter } from "next/navigation";
import { Plus, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecentChats, useCreateConversation } from "@/hooks/use-chat";
import { useChatStore } from "@/lib/stores/chat-store";
import { RecentChatCard } from "./RecentChatCard";

export function RecentChatsPanel({ workspace }: { workspace: string }) {
  const router = useRouter();
  const { data: chats, isLoading } = useRecentChats(5);
  const createConversation = useCreateConversation();
  const resetChat = useChatStore((s) => s.reset);

  const handleNew = async () => {
    resetChat();
    const conv = await createConversation.mutateAsync(undefined);
    router.push(`/${workspace}/chat/${conv.conversation_id}`);
  };

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text-primary">Recent Chats</h2>
        <Button size="sm" onClick={handleNew} disabled={createConversation.isPending}>
          <Plus className="size-4" />
          New Chat
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-xl border border-border-default bg-surface-elevated p-4">
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="mt-2 h-3 w-3/4" />
            </div>
          ))}
        </div>
      ) : !chats?.length ? (
        <div className="flex flex-col items-center rounded-xl border border-border-default bg-surface-elevated py-10 text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-accent-light">
            <MessageSquare className="h-6 w-6 text-accent-text" />
          </div>
          <p className="text-sm font-medium text-text-primary">No chats yet</p>
          <p className="mt-1 text-xs text-text-muted">Start your first chat to explore your documents.</p>
          <Button size="sm" className="mt-4" onClick={handleNew} disabled={createConversation.isPending}>
            <Plus className="size-4" />
            New Chat
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {chats.map((chat) => (
            <RecentChatCard key={chat.conversation_id} chat={chat} workspace={workspace} />
          ))}
        </div>
      )}
    </div>
  );
}
