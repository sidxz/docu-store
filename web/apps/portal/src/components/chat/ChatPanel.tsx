"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { MessageSquare, PanelLeftOpen, FileText } from "lucide-react";
import { Button } from "primereact/button";
import { Badge } from "primereact/badge";
import { useConversation, useCreateConversation, useSendMessage } from "@/hooks/use-chat";
import { useChatStore } from "@/lib/stores/chat-store";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { EmptyState } from "@/components/ui/EmptyState";
import type { SourceCitation } from "@docu-store/types";

interface ChatPanelProps {
  workspace: string;
  conversationId?: string;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  onSourcesChange: (sources: SourceCitation[]) => void;
  sourcesOpen: boolean;
  onToggleSources: () => void;
}

export function ChatPanel({
  workspace,
  conversationId,
  sidebarCollapsed,
  onToggleSidebar,
  onSourcesChange,
  sourcesOpen,
  onToggleSources,
}: ChatPanelProps) {
  const router = useRouter();
  const { data, isLoading } = useConversation(conversationId);
  const createConversation = useCreateConversation();
  const sendMessage = useSendMessage(conversationId);
  const { isStreaming, streamingContent, streamingSteps, streamingSources } =
    useChatStore();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll when streaming
  useEffect(() => {
    if (isStreaming && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [isStreaming, streamingContent]);

  // Push sources to the layout — prefer streaming sources when active, otherwise last assistant message sources
  useEffect(() => {
    if (isStreaming && streamingSources.length > 0) {
      onSourcesChange(streamingSources);
      return;
    }

    // Find last assistant message with sources
    const messages = data?.messages ?? [];
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant" && messages[i].sources.length > 0) {
        onSourcesChange(messages[i].sources);
        return;
      }
    }
    onSourcesChange([]);
  }, [isStreaming, streamingSources, data?.messages, onSourcesChange]);

  const handleSend = async (message: string) => {
    if (!conversationId) {
      const conv = await createConversation.mutateAsync();
      router.push(`/${workspace}/chat/${conv.conversation_id}`);
      return;
    }
    sendMessage.mutate(message);
  };

  // Compute source count for the toggle badge
  const sourceCount = isStreaming ? streamingSources.length : (() => {
    const msgs = data?.messages ?? [];
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === "assistant" && msgs[i].sources.length > 0) {
        return msgs[i].sources.length;
      }
    }
    return 0;
  })();

  // No conversation selected
  if (!conversationId) {
    return (
      <div className="flex flex-col h-full">
        {sidebarCollapsed && (
          <div className="p-2 border-b border-surface-200 dark:border-surface-700">
            <Button
              icon={<PanelLeftOpen className="w-4 h-4" />}
              onClick={onToggleSidebar}
              className="p-button-text p-button-sm"
              aria-label="Show sidebar"
            />
          </div>
        )}
        <div className="flex-1 flex items-center justify-center">
          <EmptyState
            icon={MessageSquare}
            title="Start a conversation"
            description="Select an existing conversation or start a new one to chat with your documents."
          />
        </div>
        <ChatInput onSend={handleSend} disabled={createConversation.isPending} />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Top bar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-surface-200 dark:border-surface-700">
        {sidebarCollapsed && (
          <Button
            icon={<PanelLeftOpen className="w-4 h-4" />}
            onClick={onToggleSidebar}
            className="p-button-text p-button-sm"
            aria-label="Show sidebar"
          />
        )}
        <h2 className="text-sm font-medium text-surface-700 dark:text-surface-300 truncate flex-1">
          {data?.conversation?.title || "Loading..."}
        </h2>
        {/* Sources toggle */}
        {sourceCount > 0 && (
          <Button
            icon={<FileText className="w-4 h-4" />}
            onClick={onToggleSources}
            className={`p-button-sm p-button-text ${sourcesOpen ? "p-button-outlined" : ""}`}
            aria-label={sourcesOpen ? "Hide sources" : "Show sources"}
            badge={String(sourceCount)}
            badgeClassName="p-badge-sm"
          />
        )}
      </div>

      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <MessageList
          messages={data?.messages ?? []}
          isLoading={isLoading}
          isStreaming={isStreaming}
          streamingContent={streamingContent}
          streamingSteps={streamingSteps}
          streamingSources={streamingSources}
          workspace={workspace}
        />
      </div>

      {/* Input */}
      <ChatInput onSend={handleSend} disabled={isStreaming} />
    </div>
  );
}
