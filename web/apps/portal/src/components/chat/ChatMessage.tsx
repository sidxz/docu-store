"use client";

import { useState, useCallback } from "react";
import { User, Bot, Loader2, ThumbsUp, ThumbsDown, Copy, Check } from "lucide-react";
import type { ChatMessage as ChatMessageType } from "@docu-store/types";
import { useDevModeStore } from "@/lib/stores/dev-mode-store";
import { useChatStore } from "@/lib/stores/chat-store";
import { useAnalytics } from "@/hooks/use-analytics";
import { AgentThinkingPanel } from "./AgentThinkingPanel";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { RichContentRenderer } from "./RichContentRenderer";

interface ChatMessageProps {
  message: ChatMessageType;
  workspace: string;
  isStreaming?: boolean;
  onFeedback?: (messageId: string, feedback: "positive" | "negative") => void;
}

export function ChatMessage({ message, workspace, isStreaming, onFeedback }: ChatMessageProps) {
  const isUser = message.role === "user";
  const devMode = useDevModeStore((s) => s.enabled);
  const { rawEvents, groundingResult } = useChatStore();
  const { trackEvent } = useAnalytics();
  const [feedbackGiven, setFeedbackGiven] = useState<"positive" | "negative" | null>(null);
  const [copied, setCopied] = useState(false);

  const handleFeedback = useCallback(
    (fb: "positive" | "negative") => {
      setFeedbackGiven(fb);
      onFeedback?.(message.message_id, fb);
    },
    [message.message_id, onFeedback],
  );

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    trackEvent("chat_answer_copied", {
      message_id: message.message_id,
      content_length: message.content.length,
    });
    setTimeout(() => setCopied(false), 2000);
  }, [message.content, message.message_id, trackEvent]);

  return (
    <div className={`group/msg flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      {/* Avatar */}
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
          isUser
            ? "bg-accent-light text-accent-text"
            : "bg-surface-elevated text-text-secondary"
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
          className={`rounded-xl px-4 py-3 max-w-full ${
            isUser
              ? "inline-block bg-accent text-text-inverse rounded-tr-sm"
              : "bg-surface-elevated text-text-primary rounded-tl-sm border border-border-subtle"
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap text-sm">{message.content}</p>
          ) : (
            <>
              {/* Grounding indicator — top-right of the reply */}
              {message.content && (
                <div className="float-right ml-3 mb-1">
                  <GroundingBar
                    isStreaming={isStreaming}
                    streamingResult={groundingResult}
                    persistedGrounded={message.agent_trace?.grounding_is_grounded ?? null}
                    persistedConfidence={message.agent_trace?.grounding_confidence ?? null}
                  />
                </div>
              )}
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <MarkdownRenderer content={message.content} messageId={message.message_id} />
                {isStreaming && !message.content && (
                  <span className="inline-block w-2 h-4 bg-text-muted animate-pulse rounded-sm" />
                )}
              </div>
              {message.structured_content && message.structured_content.length > 0 && (
                <div className="mt-3 border-t border-border-subtle pt-3">
                  <RichContentRenderer blocks={message.structured_content} workspace={workspace} />
                </div>
              )}
            </>
          )}
        </div>

        {/* Action bar: feedback + copy (assistant messages, not streaming) */}
        {!isUser && !isStreaming && message.content && onFeedback && (
          <div className="flex items-center gap-1 mt-1.5 opacity-0 group-hover/msg:opacity-100 transition-opacity">
            <button
              type="button"
              onClick={() => handleFeedback("positive")}
              disabled={feedbackGiven != null}
              className={`p-1 rounded hover:bg-surface-hover transition-colors ${feedbackGiven === "positive" ? "text-ds-success" : "text-text-muted"}`}
              aria-label="Thumbs up"
            >
              <ThumbsUp className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => handleFeedback("negative")}
              disabled={feedbackGiven != null}
              className={`p-1 rounded hover:bg-surface-hover transition-colors ${feedbackGiven === "negative" ? "text-ds-error" : "text-text-muted"}`}
              aria-label="Thumbs down"
            >
              <ThumbsDown className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={handleCopy}
              className="p-1 rounded hover:bg-surface-hover transition-colors text-text-muted"
              aria-label="Copy answer"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-ds-success" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
          </div>
        )}

        {/* Dev-mode diagnostics */}
        {devMode && !isUser && !isStreaming && message.content && (
          <div className="mt-2 rounded bg-surface-elevated px-2 py-1.5 text-[10px] font-mono text-text-muted">
            <div className="flex flex-wrap gap-x-3 gap-y-0.5">
              <span className="font-semibold text-text-secondary">msg</span>
              <span>chars: <span className="text-accent-text">{message.content.length}</span></span>
              <span>sources: <span className="text-feature-search">{message.sources.length}</span></span>
              {message.agent_trace?.total_duration_ms != null && (
                <span>pipeline: <span className="text-ds-success">{message.agent_trace.total_duration_ms}ms</span></span>
              )}
              {message.agent_trace?.retry_count != null && message.agent_trace.retry_count > 0 && (
                <span className="text-ds-warning">retries: {message.agent_trace.retry_count}</span>
              )}
            </div>
          </div>
        )}

        {devMode && !isUser && isStreaming && (
          <div className="mt-2 rounded bg-surface-elevated px-2 py-1.5 text-[10px] font-mono text-text-muted">
            <div className="flex flex-wrap gap-x-3 gap-y-0.5">
              <span className="font-semibold text-text-secondary">stream</span>
              <span>events: <span className="text-accent-text">{rawEvents.length}</span></span>
              <span>chars: <span className="text-feature-search">{message.content.length}</span></span>
              <span>grounding: <span className={groundingResult ? "text-ds-success" : "text-ds-warning"}>{groundingResult ? "done" : "pending"}</span></span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Simple grounding bar ────────────────────────────────────────────────────

function GroundingBar({
  isStreaming,
  streamingResult,
  persistedGrounded,
  persistedConfidence,
}: {
  isStreaming?: boolean;
  streamingResult: { is_grounded: boolean; confidence: number } | null;
  persistedGrounded: boolean | null;
  persistedConfidence: number | null;
}) {
  // Resolve grounding data: prefer streaming result, fall back to persisted
  const isGrounded = isStreaming ? streamingResult?.is_grounded : (persistedGrounded ?? streamingResult?.is_grounded);
  const confidence = isStreaming ? streamingResult?.confidence : (persistedConfidence ?? streamingResult?.confidence);

  // Pending: streaming and no result yet
  if (isStreaming && confidence == null) {
    return (
      <div className="mt-1.5 flex items-center gap-2 text-xs text-ds-warning">
        <Loader2 className="w-3 h-3 animate-spin" />
        <span>Pending verification</span>
      </div>
    );
  }

  // No grounding data at all (old messages before this feature)
  if (confidence == null) return null;

  const pct = Math.round(confidence * 100);

  return (
    <div className="mt-1.5 flex items-center gap-2 text-xs">
      <span className="text-text-muted">Grounding Score</span>
      <div className="h-1.5 w-20 rounded-full bg-border-subtle overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${getBarColor(confidence)}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-text-secondary font-medium tabular-nums">{pct}%</span>
    </div>
  );
}

function getBarColor(score: number): string {
  if (score >= 0.8) return "bg-score-excellent";
  if (score >= 0.6) return "bg-score-good";
  if (score >= 0.4) return "bg-score-fair";
  return "bg-score-poor";
}
