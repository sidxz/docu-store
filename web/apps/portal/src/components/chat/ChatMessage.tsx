"use client";

import { User, Bot } from "lucide-react";
import type { ChatMessage as ChatMessageType } from "@docu-store/types";
import { useDevModeStore } from "@/lib/stores/dev-mode-store";
import { useChatStore } from "@/lib/stores/chat-store";
import { AgentThinkingPanel } from "./AgentThinkingPanel";
import { MarkdownRenderer } from "./MarkdownRenderer";

interface ChatMessageProps {
  message: ChatMessageType;
  workspace: string;
  isStreaming?: boolean;
}

export function ChatMessage({ message, workspace, isStreaming }: ChatMessageProps) {
  const isUser = message.role === "user";
  const devMode = useDevModeStore((s) => s.enabled);
  const { rawEvents } = useChatStore();

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      {/* Avatar */}
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
          isUser
            ? "bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400"
            : "bg-surface-100 dark:bg-surface-800 text-surface-600 dark:text-surface-400"
        }`}
      >
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>

      {/* Content */}
      <div className={`flex-1 min-w-0 ${isUser ? "text-right" : ""}`}>
        {/* Agent thinking panel (assistant only) */}
        {!isUser && message.agent_trace && (
          <AgentThinkingPanel
            trace={message.agent_trace}
            isStreaming={isStreaming}
          />
        )}

        {/* Message body */}
        <div
          className={`inline-block rounded-xl px-4 py-3 max-w-full ${
            isUser
              ? "bg-primary-600 text-white dark:bg-primary-700 rounded-tr-sm"
              : "bg-surface-50 dark:bg-surface-800 text-surface-900 dark:text-surface-100 rounded-tl-sm"
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap text-sm">{message.content}</p>
          ) : (
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <MarkdownRenderer content={message.content} />
              {isStreaming && !message.content && (
                <span className="inline-block w-2 h-4 bg-surface-400 dark:bg-surface-500 animate-pulse rounded-sm" />
              )}
            </div>
          )}
        </div>

        {/* Dev-mode: message diagnostics for persisted messages */}
        {devMode && !isUser && !isStreaming && message.content && (
          <div className="mt-2 rounded bg-surface-100 dark:bg-surface-800 px-2 py-1.5 text-[10px] font-mono text-surface-500 dark:text-surface-400">
            <div className="flex flex-wrap gap-x-3 gap-y-0.5">
              <span className="font-semibold text-surface-600 dark:text-surface-300">msg</span>
              <span>chars: <span className="text-blue-500">{message.content.length}</span></span>
              <span>sources: <span className="text-purple-500">{message.sources.length}</span></span>
              {message.agent_trace?.total_duration_ms != null && (
                <span>pipeline: <span className="text-green-500">{message.agent_trace.total_duration_ms}ms</span></span>
              )}
              {message.agent_trace?.retry_count != null && message.agent_trace.retry_count > 0 && (
                <span className="text-orange-400">retries: {message.agent_trace.retry_count}</span>
              )}
              {message.token_usage && (
                <span>tokens: <span className="text-blue-500">p:{message.token_usage.prompt} c:{message.token_usage.completion}</span></span>
              )}
            </div>
          </div>
        )}

        {/* Dev-mode: streaming diagnostics (only during active stream) */}
        {devMode && !isUser && isStreaming && (
          <div className="mt-2 rounded bg-surface-100 dark:bg-surface-800 px-2 py-1.5 text-[10px] font-mono text-surface-500 dark:text-surface-400">
            <div className="flex flex-wrap gap-x-3 gap-y-0.5">
              <span className="font-semibold text-surface-600 dark:text-surface-300">stream</span>
              <span>events: <span className="text-blue-500">{rawEvents.length}</span></span>
              <span>chars: <span className="text-purple-500">{message.content.length}</span></span>
              <span>sources: <span className="text-green-500">{message.sources.length}</span></span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
