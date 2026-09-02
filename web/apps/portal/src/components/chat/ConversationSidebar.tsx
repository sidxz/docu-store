"use client";

import { useRouter } from "next/navigation";
import { Plus, Trash2, MessageSquare, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useConversations, useCreateConversation, useDeleteConversation } from "@/hooks/use-chat";
import { useConfirm } from "@/components/providers/ConfirmProvider";
import { useChatStore } from "@/lib/stores/chat-store";
import type { Conversation } from "@docu-store/types";

interface ConversationSidebarProps {
  workspace: string;
  activeConversationId?: string;
  onCollapse: () => void;
  /** Route segment to navigate within, so selecting a conversation keeps you on
   *  the surface you are already on. */
  basePath?: string;
}

export function ConversationSidebar({
  workspace,
  activeConversationId,
  onCollapse,
  basePath = "chat",
}: ConversationSidebarProps) {
  const router = useRouter();
  const { data: conversations, isLoading } = useConversations();
  const createConversation = useCreateConversation();
  const deleteConversation = useDeleteConversation();
  const confirm = useConfirm();

  const resetChat = useChatStore((s) => s.reset);
  const unreadAnswers = useChatStore((s) => s.unreadAnswers);

  const handleNew = async () => {
    const conv = await createConversation.mutateAsync(undefined);
    router.push(`/${workspace}/${basePath}/${conv.conversation_id}`);
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (
      !(await confirm({
        title: "Delete research session?",
        description: "This conversation and its messages will be permanently deleted.",
        confirmLabel: "Delete",
        destructive: true,
      }))
    ) {
      return;
    }
    await deleteConversation.mutateAsync(id);
    useChatStore.getState().clearUnread(id);
    if (id === activeConversationId) {
      resetChat();
      router.push(`/${workspace}/${basePath}`);
    }
  };

  const handleSelect = (id: string) => {
    router.push(`/${workspace}/${basePath}/${id}`);
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
          New Research
        </Button>
      </div>

      {/* Conversation list — native overflow, NOT Radix ScrollArea: its
          display:table viewport sizes to content, which defeats `truncate`
          and pushes the per-row delete button outside the w-72 column. */}
      <div className="flex-1 overflow-y-auto">
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
                isUnread={unreadAnswers.includes(conv.conversation_id)}
                onSelect={handleSelect}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ConversationItem({
  conversation,
  isActive,
  isUnread,
  onSelect,
  onDelete,
}: {
  conversation: Conversation;
  isActive: boolean;
  isUnread: boolean;
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
      {isUnread && (
        <span
          className="size-2 shrink-0 rounded-full bg-accent-text"
          role="status"
          aria-label="Unread answer"
        />
      )}
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
