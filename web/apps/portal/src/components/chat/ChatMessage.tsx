"use client";

import { useState, useCallback } from "react";
import { User, Bot, Loader2, ThumbsUp, ThumbsDown, Copy, Check } from "lucide-react";
import type { ChatMessage as ChatMessageType } from "@docu-store/types";
import { useDevModeStore } from "@/lib/stores/dev-mode-store";
import { useChatStore } from "@/lib/stores/chat-store";
import { useAnalytics } from "@/hooks/use-analytics";
import { Loader } from "@/components/ai-elements/loader";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Message, MessageContent, MessageActions, MessageAction } from "@/components/ai-elements/message";
import { AgentThinkingPanel } from "./AgentThinkingPanel";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { ReasoningDisclosure } from "./ReasoningDisclosure";
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

  // Bubble chrome per role, expressed with the SAME group-scoped modifiers
  // MessageContent's own defaults use (group-[.is-user]:/group-[.is-assistant]:)
  // so these overrides dedupe cleanly against them instead of racing on
  // cascade order. ponytail: keeps this a plain string instead of a cn() call
  // — nothing here conflicts within a single role.
  const bubbleClassName = isUser
    ? "group-[.is-user]:rounded-xl group-[.is-user]:rounded-tr-sm group-[.is-user]:bg-primary group-[.is-user]:text-text-inverse"
    : "group-[.is-assistant]:w-full group-[.is-assistant]:rounded-xl group-[.is-assistant]:rounded-tl-sm group-[.is-assistant]:border group-[.is-assistant]:border-border-subtle group-[.is-assistant]:bg-surface-elevated group-[.is-assistant]:px-4 group-[.is-assistant]:py-3 group-[.is-assistant]:text-text-primary";

  return (
    <div className={`group/msg flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      {/* Avatar — no MessageAvatar export exists in the vendored AI Elements
          set (registry drift, see task-2-report.md), so this stays custom. */}
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
      {/* gap-0: siblings below already carry their own mt-* spacing (and
          AgentThinkingPanel/ReasoningDisclosure their own mb-2), so Message's
          default gap-2 would double up. max-w-full overrides Message's
          default max-w-[95%] to match the original's unconstrained column. */}
      <Message from={message.role} className="flex-1 min-w-0 max-w-full gap-0">
        {/* Agent thinking panel (assistant only) */}
        {!isUser && message.agent_trace && (
          <AgentThinkingPanel
            trace={message.agent_trace}
            isStreaming={isStreaming}
          />
        )}

        {/* Model reasoning disclosure (assistant only) */}
        {!isUser && message.agent_trace?.reasoning_content && (
          <ReasoningDisclosure reasoning={message.agent_trace.reasoning_content} isStreaming={isStreaming} />
        )}

        {/* Message body */}
        <MessageContent className={bubbleClassName}>
          {isUser ? (
            <p className="whitespace-pre-wrap text-right text-sm">{message.content}</p>
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
                {isStreaming && !message.content && <ThinkingIndicator />}
              </div>
              {message.structured_content && message.structured_content.length > 0 && (
                <div className="mt-3 border-t border-border-subtle pt-3">
                  <RichContentRenderer blocks={message.structured_content} workspace={workspace} />
                </div>
              )}
            </>
          )}
        </MessageContent>

        {/* Action bar: feedback + copy (assistant messages, not streaming) */}
        {!isUser && !isStreaming && message.content && onFeedback && (
          <MessageActions className="mt-1.5 opacity-0 transition-opacity group-hover/msg:opacity-100">
            <MessageAction
              label="Thumbs up"
              onClick={() => handleFeedback("positive")}
              disabled={feedbackGiven != null}
              className={`hover:bg-surface-hover ${feedbackGiven === "positive" ? "text-ds-success" : "text-text-muted"}`}
            >
              <ThumbsUp className="size-3.5" />
            </MessageAction>
            <MessageAction
              label="Thumbs down"
              onClick={() => handleFeedback("negative")}
              disabled={feedbackGiven != null}
              className={`hover:bg-surface-hover ${feedbackGiven === "negative" ? "text-ds-error" : "text-text-muted"}`}
            >
              <ThumbsDown className="size-3.5" />
            </MessageAction>
            <MessageAction
              label="Copy answer"
              onClick={handleCopy}
              className="hover:bg-surface-hover text-text-muted"
            >
              {copied ? <Check className="size-3.5 text-ds-success" /> : <Copy className="size-3.5" />}
            </MessageAction>
          </MessageActions>
        )}

        {/* Token usage — per-message, persisted (visible to all, not just dev).
            Not AI Elements <Context>: Context requires maxTokens (a model
            context-window budget) plus an ai-SDK-shaped LanguageModelUsage
            object with a modelId for tokenlens cost lookups. docu-store's
            TokenUsage is just { prompt, completion, total } — no window
            budget, no per-message model id — so there's no real
            usedTokens/maxTokens ratio or cost to render. Kept custom,
            restyled font-mono/tabular-nums. */}
        {!isUser && !isStreaming && message.token_usage && (
          <div
            className="mt-1 font-mono text-[11px] text-text-muted tabular-nums"
            title={`${message.token_usage.prompt.toLocaleString()} prompt + ${message.token_usage.completion.toLocaleString()} completion`}
          >
            {message.token_usage.total.toLocaleString()} tokens
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
      </Message>
    </div>
  );
}

// Animated "assistant is working" indicator — shown after send, before the first
// answer token arrives (otherwise the empty bubble reads as hung).
function ThinkingIndicator() {
  return (
    <div className="inline-flex items-center gap-2 text-sm text-text-muted">
      <Loader size={14} />
      <Shimmer as="span" duration={1.5}>
        Working…
      </Shimmer>
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
      <span className="text-text-secondary font-mono font-medium tabular-nums">{pct}%</span>
    </div>
  );
}

function getBarColor(score: number): string {
  if (score >= 0.8) return "bg-score-excellent";
  if (score >= 0.6) return "bg-score-good";
  if (score >= 0.4) return "bg-score-fair";
  return "bg-score-poor";
}
