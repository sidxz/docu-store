"use client";

import { useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { MessageSquare, PanelLeftOpen, FileText } from "lucide-react";
import { Button } from "primereact/button";
import { Badge } from "primereact/badge";
import { useConversation, useCreateConversation, useSendMessage, useChatFeedback } from "@/hooks/use-chat";
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

  // Abort in-flight SSE stream on unmount (e.g. navigating away from chat)
  useEffect(() => () => sendMessage.abort(), []); // eslint-disable-line react-hooks/exhaustive-deps
  const feedbackMutation = useChatFeedback(conversationId);
  const { isStreaming, streamingContent, streamingSteps, streamingSources, chatMode } =
    useChatStore();
  const planningSummary = useChatStore((s) => {
    const step = s.streamingSteps.find((st) => st.step === "planning" && st.status === "completed");
    if (!step?.thinking_content) return null;
    try {
      const match = step.thinking_content.match(/```json\s*\n([\s\S]*?)\n```/);
      const parsed = JSON.parse(match ? match[1] : step.thinking_content);
      return (parsed?.reformulated_query as string) || null;
    } catch {
      return null;
    }
  });
  const pendingUserMessage = useChatStore((s) => s.pendingUserMessage);
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleFeedback = useCallback(
    (messageId: string, feedback: "positive" | "negative") => {
      feedbackMutation.mutate({ messageId, feedback, mode: chatMode });
    },
    [feedbackMutation, chatMode],
  );

  // Auto-scroll when streaming
  useEffect(() => {
    if (isStreaming && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [isStreaming, streamingContent]);

  // Push sources to the layout.
  // Priority: activeSourcesMessageId (user clicked citation) > finalSources (cited-only after done)
  //         > streamingSources (all retrieved during streaming) > persisted message sources
  const doneEvent = useChatStore((s) => s.doneEvent);
  const finalSources = useChatStore((s) => s.finalSources);
  const activeSourcesMessageId = useChatStore((s) => s.activeSourcesMessageId);

  useEffect(() => {
    const messages = data?.messages ?? [];

    // 1. User clicked a citation in a specific message — show THAT message's sources
    if (activeSourcesMessageId) {
      if (activeSourcesMessageId === "streaming") {
        // For the streaming message, prefer finalSources (cited-only) if available
        onSourcesChange(finalSources ?? streamingSources);
        return;
      }
      const targetMsg = messages.find((m) => m.message_id === activeSourcesMessageId);
      if (targetMsg && targetMsg.sources.length > 0) {
        onSourcesChange(targetMsg.sources);
        return;
      }
    }

    // 2. Answer complete — show only cited sources (finalSources from done event)
    if (finalSources && finalSources.length > 0) {
      const apiHasCaughtUp = doneEvent?.message_id
        ? messages.some((m) => m.message_id === doneEvent.message_id)
        : false;
      if (!apiHasCaughtUp) {
        onSourcesChange(finalSources);
        return;
      }
    }

    // 3. Still streaming — show all retrieved sources
    if (isStreaming && streamingSources.length > 0) {
      onSourcesChange(streamingSources);
      return;
    }

    // Default: last assistant message sources
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant" && messages[i].sources.length > 0) {
        onSourcesChange(messages[i].sources);
        return;
      }
    }
    onSourcesChange([]);
  }, [isStreaming, streamingSources, finalSources, data?.messages, doneEvent, activeSourcesMessageId, onSourcesChange]);

  // Auto-send queued message after navigating to a new conversation
  const queuedMessage = useChatStore((s) => s.queuedMessage);
  const setQueuedMessage = useChatStore((s) => s.setQueuedMessage);
  const queueSentRef = useRef(false);

  useEffect(() => {
    if (conversationId && queuedMessage && !isStreaming && !queueSentRef.current) {
      queueSentRef.current = true;
      setQueuedMessage(null);
      sendMessage.mutate(queuedMessage);
    }
    if (!queuedMessage) {
      queueSentRef.current = false;
    }
  }, [conversationId, queuedMessage]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSend = async (message: string) => {
    if (!conversationId) {
      // Queue the message, create conversation, then navigate — message auto-sends on mount
      setQueuedMessage(message);
      const conv = await createConversation.mutateAsync(undefined);
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
          <div className="p-2 border-b border-border-default">
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
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border-default">
        {sidebarCollapsed && (
          <Button
            icon={<PanelLeftOpen className="w-4 h-4" />}
            onClick={onToggleSidebar}
            className="p-button-text p-button-sm"
            aria-label="Show sidebar"
          />
        )}
        <h2 className="text-sm font-medium text-text-primary truncate flex-1">
          {data?.title
            || planningSummary
            || pendingUserMessage
            || (isLoading ? "" : "New Chat")}
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
          onFeedback={handleFeedback}
        />
      </div>

      {/* Input */}
      <ChatInput onSend={handleSend} disabled={isStreaming} />
    </div>
  );
}
