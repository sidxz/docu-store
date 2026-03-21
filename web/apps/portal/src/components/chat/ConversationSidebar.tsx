"use client";

import { useRouter } from "next/navigation";
import { Plus, Trash2, MessageSquare } from "lucide-react";
import { Button } from "primereact/button";
import { useConversations, useCreateConversation, useDeleteConversation } from "@/hooks/use-chat";
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

  const handleNew = async () => {
    const conv = await createConversation.mutateAsync();
    router.push(`/${workspace}/chat/${conv.conversation_id}`);
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    await deleteConversation.mutateAsync(id);
    if (id === activeConversationId) {
      router.push(`/${workspace}/chat`);
    }
  };

  const handleSelect = (id: string) => {
    router.push(`/${workspace}/chat/${id}`);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-3 border-b border-surface-200 dark:border-surface-700">
        <Button
          label="New Chat"
          icon={<Plus className="w-4 h-4 mr-2" />}
          onClick={handleNew}
          loading={createConversation.isPending}
          className="w-full p-button-sm"
          severity="secondary"
          outlined
        />
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 bg-surface-100 dark:bg-surface-800 rounded animate-pulse" />
            ))}
          </div>
        ) : !conversations?.length ? (
          <div className="p-4 text-center text-surface-500 text-sm">
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
      </div>
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
      className={`group flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${
        isActive
          ? "bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300"
          : "hover:bg-surface-100 dark:hover:bg-surface-800 text-surface-700 dark:text-surface-300"
      }`}
    >
      <MessageSquare className="w-4 h-4 flex-shrink-0 opacity-60" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{title}</p>
        <p className="text-xs text-surface-500 dark:text-surface-400">
          {date} · {conversation.message_count} msgs
        </p>
      </div>
      <button
        onClick={(e) => onDelete(e, conversation.conversation_id)}
        className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-surface-200 dark:hover:bg-surface-700 transition-opacity"
      >
        <Trash2 className="w-3.5 h-3.5 text-surface-500" />
      </button>
    </div>
  );
}
