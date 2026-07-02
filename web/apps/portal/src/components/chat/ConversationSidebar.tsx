"use client";

import { useRouter } from "next/navigation";
import { Plus, Trash2, MessageSquare, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { useConversations, useCreateConversation, useDeleteConversation } from "@/hooks/use-chat";
import { useChatStore } from "@/lib/stores/chat-store";
import type { Conversation } from "@docu-store/types";

interface ConversationSidebarProps {
  workspace: string;
  activeConversationId?: string;
  onCollapse: () => void;
}

export function ConversationSidebar({
  workspace,
  activeConversationId,
  onCollapse,
}: ConversationSidebarProps) {
  const router = useRouter();
  const { data: conversations, isLoading } = useConversations();
  const createConversation = useCreateConversation();
  const deleteConversation = useDeleteConversation();

  const resetChat = useChatStore((s) => s.reset);

  const handleNew = async () => {
    resetChat();
    const conv = await createConversation.mutateAsync(undefined);
    router.push(`/${workspace}/chat/${conv.conversation_id}`);
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    await deleteConversation.mutateAsync(id);
    if (id === activeConversationId) {
      resetChat();
      router.push(`/${workspace}/chat`);
    }
  };

  const handleSelect = (id: string) => {
    resetChat();
    router.push(`/${workspace}/chat/${id}`);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-2 border-b border-border-default">
        <Button
          variant="outline"
          size="sm"
          onClick={handleNew}
          disabled={createConversation.isPending}
          className="w-full"
        >
          {createConversation.isPending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Plus className="size-4" />
          )}
          New Chat
        </Button>
      </div>

      {/* Conversation list */}
      <ScrollArea className="flex-1">
        {isLoading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 bg-surface-elevated rounded animate-pulse" />
            ))}
          </div>
        ) : !conversations?.length ? (
          <div className="p-4 text-center text-text-muted text-sm">
            <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-40" />
            <p>No conversations yet</p>
          </div>
        ) : (
          <div className="p-2 space-y-1">
            {conversations.map((conv: Conversation) => (
              <ConversationItem
                key={conv.conversation_id}
                conversation={conv}
                isActive={conv.conversation_id === activeConversationId}
                onSelect={handleSelect}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}

function ConversationItem({
  conversation,
  isActive,
  onSelect,
  onDelete,
}: {
  conversation: Conversation;
  isActive: boolean;
  onSelect: (id: string) => void;
  onDelete: (e: React.MouseEvent, id: string) => void;
}) {
  const title = conversation.title || "Untitled";
  const date = new Date(conversation.updated_at).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });

  return (
    <div
      onClick={() => onSelect(conversation.conversation_id)}
      className={cn(
        "group flex items-center gap-2 rounded-lg px-3 py-2.5 cursor-pointer transition-colors",
        isActive
          ? "bg-accent-muted text-accent-text"
          : "text-text-primary hover:bg-surface-hover",
      )}
    >
      <MessageSquare className="size-4 shrink-0 opacity-60" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{title}</p>
        <p className="text-xs text-text-muted">
          {date} · {conversation.message_count} msgs
        </p>
      </div>
      <button
        onClick={(e) => onDelete(e, conversation.conversation_id)}
        className="rounded p-1 opacity-0 transition-opacity hover:bg-surface-hover group-hover:opacity-100"
        aria-label="Delete conversation"
      >
        <Trash2 className="size-3.5 text-text-muted" />
      </button>
    </div>
  );
}
