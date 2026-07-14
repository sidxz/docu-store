"use client";

import type { ChatMessage as ChatMessageType, AgentStep, SourceCitation } from "@docu-store/types";
import { ConversationEmptyState } from "@/components/ai-elements/conversation";
import { Skeleton } from "@/components/ui/skeleton";
import { useChatStore } from "@/lib/stores/chat-store";
import { ChatMessage } from "./ChatMessage";

interface MessageListProps {
  messages: ChatMessageType[];
  isLoading: boolean;
  isStreaming: boolean;
  streamingContent: string;
  streamingSteps: AgentStep[];
  streamingSources: SourceCitation[];
  workspace: string;
  conversationId?: string;
  onFeedback?: (messageId: string, feedback: "positive" | "negative") => void;
}

export function MessageList({
  messages,
  isLoading,
  isStreaming,
  streamingContent,
  streamingSteps,
  streamingSources,
  workspace,
  conversationId,
  onFeedback,
}: MessageListProps) {
  const pendingUserMessage = useChatStore((s) => s.pendingUserMessage);
  const finalSources = useChatStore((s) => s.finalSources);
  const groundingResult = useChatStore((s) => s.groundingResult);
  const streamingStructuredBlocks = useChatStore((s) => s.streamingStructuredBlocks);
  const streamingReasoning = useChatStore((s) => s.streamingReasoning);
  const doneEvent = useChatStore((s) => s.doneEvent);
  const streamingConversationId = useChatStore((s) => s.streamingConversationId);

  // Determine if the API data already includes the response we just streamed.
  // If the done event has a message_id, check if the messages array contains it.
  const apiHasCaughtUp = doneEvent?.message_id
    ? messages.some((m) => m.message_id === doneEvent.message_id)
    : false;

  // Show the optimistic messages (pending user + streaming assistant) when the
  // buffered stream belongs to THIS conversation (the store is global — without
  // this, another conversation's leftover stream/error ghost-renders here) and:
  // - Currently streaming, OR
  // - Streaming finished but the API refetch hasn't returned the new messages yet
  const streamBelongsHere = streamingConversationId === conversationId;
  const showOptimistic = streamBelongsHere && (isStreaming || (streamingContent && !apiHasCaughtUp));

  // Renders as fragment children of ConversationContent — its gap handles
  // message spacing, ChatPanel constrains the column width.
  if (isLoading) {
    return (
      <>
        {[1, 2, 3].map((i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        ))}
      </>
    );
  }

  return (
    <>
      {messages.map((msg) => (
        <ChatMessage key={msg.message_id} message={msg} workspace={workspace} onFeedback={onFeedback} />
      ))}

      {/* Show user message immediately — persists until API catches up */}
      {showOptimistic && pendingUserMessage && (
        <ChatMessage
          message={{
            conversation_id: "",
            message_id: "pending-user",
            role: "user",
            content: pendingUserMessage,
            sources: [],
            agent_trace: null,
            structured_content: null,
            token_usage: null,
            created_at: new Date().toISOString(),
          }}
          workspace={workspace}
        />
      )}

      {/* Streaming / just-completed assistant message — persists until API catches up */}
      {showOptimistic && (
        <ChatMessage
          message={{
            conversation_id: "",
            message_id: "streaming",
            role: "assistant",
            content: streamingContent,
            sources: finalSources ?? streamingSources,
            agent_trace: {
              steps: streamingSteps,
              total_duration_ms: doneEvent?.duration_ms ?? null,
              retry_count: 0,
              grounding_is_grounded: groundingResult?.is_grounded ?? null,
              grounding_confidence: groundingResult?.confidence ?? null,
              reasoning_content: streamingReasoning || undefined,
            },
            structured_content: streamingStructuredBlocks.length > 0 ? streamingStructuredBlocks : null,
            token_usage: null,
            created_at: new Date().toISOString(),
          }}
          workspace={workspace}
          isStreaming={isStreaming}
        />
      )}

      {messages.length === 0 && !showOptimistic && (
        <ConversationEmptyState
          title="Ask a question about your documents"
          description="Your answers will be grounded in uploaded sources with citations."
          className="py-12"
        />
      )}
    </>
  );
}
