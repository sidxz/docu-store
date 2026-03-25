"use client";

import type { ChatMessage as ChatMessageType, AgentStep, SourceCitation } from "@docu-store/types";
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
  onFeedback,
}: MessageListProps) {
  const pendingUserMessage = useChatStore((s) => s.pendingUserMessage);
  const finalSources = useChatStore((s) => s.finalSources);
  const groundingResult = useChatStore((s) => s.groundingResult);
  const doneEvent = useChatStore((s) => s.doneEvent);

  // Determine if the API data already includes the response we just streamed.
  // If the done event has a message_id, check if the messages array contains it.
  const apiHasCaughtUp = doneEvent?.message_id
    ? messages.some((m) => m.message_id === doneEvent.message_id)
    : false;

  // Show the optimistic messages (pending user + streaming assistant) when:
  // - Currently streaming, OR
  // - Streaming finished but the API refetch hasn't returned the new messages yet
  const showOptimistic = isStreaming || (streamingContent && !apiHasCaughtUp);

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto p-6 space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-border-subtle animate-pulse flex-shrink-0" />
            <div className="flex-1 space-y-2">
              <div className="h-4 bg-border-subtle rounded animate-pulse w-3/4" />
              <div className="h-4 bg-border-subtle rounded animate-pulse w-1/2" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
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
            },
            structured_content: null,
            token_usage: null,
            created_at: new Date().toISOString(),
          }}
          workspace={workspace}
          isStreaming={isStreaming}
        />
      )}

      {messages.length === 0 && !showOptimistic && (
        <div className="text-center text-text-muted py-12">
          <p className="text-lg">Ask a question about your documents</p>
          <p className="text-sm mt-1">
            Your answers will be grounded in uploaded sources with citations.
          </p>
        </div>
      )}
    </div>
  );
}
