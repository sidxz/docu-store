"use client";

import type { ChatMessage as ChatMessageType, AgentStep, SourceCitation } from "@docu-store/types";
import { ChatMessage } from "./ChatMessage";

interface MessageListProps {
  messages: ChatMessageType[];
  isLoading: boolean;
  isStreaming: boolean;
  streamingContent: string;
  streamingSteps: AgentStep[];
  streamingSources: SourceCitation[];
  workspace: string;
}

export function MessageList({
  messages,
  isLoading,
  isStreaming,
  streamingContent,
  streamingSteps,
  streamingSources,
  workspace,
}: MessageListProps) {
  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto p-6 space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-surface-200 dark:bg-surface-700 animate-pulse flex-shrink-0" />
            <div className="flex-1 space-y-2">
              <div className="h-4 bg-surface-200 dark:bg-surface-700 rounded animate-pulse w-3/4" />
              <div className="h-4 bg-surface-200 dark:bg-surface-700 rounded animate-pulse w-1/2" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      {messages.map((msg) => (
        <ChatMessage key={msg.message_id} message={msg} workspace={workspace} />
      ))}

      {/* Streaming assistant message */}
      {isStreaming && (
        <ChatMessage
          message={{
            conversation_id: "",
            message_id: "streaming",
            role: "assistant",
            content: streamingContent,
            sources: streamingSources,
            agent_trace: {
              steps: streamingSteps,
              total_duration_ms: null,
              retry_count: 0,
            },
            structured_content: null,
            token_usage: null,
            created_at: new Date().toISOString(),
          }}
          workspace={workspace}
          isStreaming
        />
      )}

      {messages.length === 0 && !isStreaming && (
        <div className="text-center text-surface-400 dark:text-surface-500 py-12">
          <p className="text-lg">Ask a question about your documents</p>
          <p className="text-sm mt-1">
            Your answers will be grounded in uploaded sources with citations.
          </p>
        </div>
      )}
    </div>
  );
}
