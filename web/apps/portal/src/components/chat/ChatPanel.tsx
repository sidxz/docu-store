"use client";

import { useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { PanelLeftOpen, FileText, Folder } from "lucide-react";
import { SURFACES, surfaceFromBasePath, conversationHref } from "@/lib/surfaces";
import { Button } from "@/components/ui/button";
import { MoveToFolderMenu } from "@/components/folders/MoveToFolderMenu";
import { useFolders } from "@/hooks/use-folders";
import { Badge } from "@/components/ui/badge";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import { useConversation, useCreateConversation, useSendMessage, useChatFeedback } from "@/hooks/use-chat";
import { useChatStore } from "@/lib/stores/chat-store";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatTokens } from "@/lib/utils";
import type { ChatSurface, SourceCitation } from "@docu-store/types";

interface ChatPanelProps {
  workspace: string;
  conversationId?: string;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  onSourcesChange: (sources: SourceCitation[]) => void;
  sourcesOpen: boolean;
  onToggleSources: () => void;
  /** Pins the pipeline for this surface, so Literature cannot change the mode
   *  the user chose for Deep Research. Omitted = follow the store. */
  forceMode?: string;
  /** Composer prompt, since the two surfaces search different things. */
  placeholder?: string;
  /** Route segment this panel lives under, so a new conversation stays on the
   *  surface it was started from. */
  basePath?: string;
}

export function ChatPanel({
  workspace,
  conversationId,
  sidebarCollapsed,
  onToggleSidebar,
  onSourcesChange,
  sourcesOpen,
  onToggleSources,
  forceMode,
  basePath = SURFACES.research.segment,
  placeholder,
}: ChatPanelProps) {
  const router = useRouter();
  const { data, isLoading } = useConversation(conversationId);
  const { data: folders } = useFolders();
  const surface: ChatSurface = surfaceFromBasePath(basePath);
  const createConversation = useCreateConversation(surface);
  const sendMessage = useSendMessage(conversationId, { forceMode });

  const feedbackMutation = useChatFeedback(conversationId);
  const { isStreaming, streamingContent, streamingSteps, streamingSources, chatMode } =
    useChatStore();
  const streamingConversationId = useChatStore((s) => s.streamingConversationId);
  // The store is global and streams now outlive their page — only treat this
  // conversation as busy when the live stream actually belongs to it.
  const streamingHere = isStreaming && streamingConversationId === conversationId;
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
  // Only surface the pending message when its stream belongs to this
  // conversation — the store is global and leaks across navigation otherwise.
  const pendingUserMessage = useChatStore((s) =>
    s.streamingConversationId === conversationId ? s.pendingUserMessage : null,
  );

  const handleFeedback = useCallback(
    (messageId: string, feedback: "positive" | "negative") => {
      feedbackMutation.mutate({ messageId, feedback, mode: chatMode });
    },
    [feedbackMutation, chatMode],
  );

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
    if (streamingConversationId === conversationId && finalSources && finalSources.length > 0) {
      const apiHasCaughtUp = doneEvent?.message_id
        ? messages.some((m) => m.message_id === doneEvent.message_id)
        : false;
      if (!apiHasCaughtUp) {
        onSourcesChange(finalSources);
        return;
      }
    }

    // 3. Still streaming — show all retrieved sources
    if (streamingHere && streamingSources.length > 0) {
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
  }, [isStreaming, streamingHere, streamingConversationId, conversationId, streamingSources, finalSources, data?.messages, doneEvent, activeSourcesMessageId, onSourcesChange]);

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

  // Reattach to a server-side run after a reload (or a 409): the detail
  // endpoint says one is active and no local stream owns this conversation.
  // resume() itself is idempotent, so firing on refetches is harmless.
  useEffect(() => {
    if (data?.active_run) void sendMessage.resume();
  }, [data?.active_run, conversationId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSend = async (message: string) => {
    if (!conversationId) {
      // Queue the message, create conversation, then navigate — message auto-sends on mount
      setQueuedMessage(message);
      const conv = await createConversation.mutateAsync(undefined);
      router.push(conversationHref(workspace, surface, conv.conversation_id));
      return;
    }
    sendMessage.mutate(message);
  };

  // Compute source count for the toggle badge
  const sourceCount = streamingHere ? streamingSources.length : (() => {
    const msgs = data?.messages ?? [];
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === "assistant" && msgs[i].sources.length > 0) {
        return msgs[i].sources.length;
      }
    }
    return 0;
  })();

  // Total tokens for this chat (sum of persisted per-message usage)
  const chatTokens = (data?.messages ?? []).reduce(
    (sum, m) => sum + (m.token_usage?.total ?? 0),
    0,
  );

  // No conversation selected
  if (!conversationId) {
    return (
      <div className="flex flex-col h-full">
        {sidebarCollapsed && (
          <div className="p-2 border-b border-border-default">
            <Button variant="ghost" size="icon-sm" onClick={onToggleSidebar} aria-label="Show sidebar">
              <PanelLeftOpen className="size-4" />
            </Button>
          </div>
        )}
        <div className="flex-1 flex items-center justify-center">
          {/* The two surfaces search different corpora — the empty state has to
              say which, and wear the same icon and colour as its sidebar entry. */}
          <EmptyState
            icon={SURFACES[surface].icon}
            iconColor={SURFACES[surface].iconColor}
            title={SURFACES[surface].emptyTitle}
            description={SURFACES[surface].emptyDescription}
          />
        </div>
        <ChatInput onSend={handleSend} disabled={createConversation.isPending} onAbort={sendMessage.stop} modeLocked={!!forceMode} placeholder={placeholder} />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Top bar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border-default">
        {sidebarCollapsed && (
          <Button variant="ghost" size="icon-sm" onClick={onToggleSidebar} aria-label="Show sidebar">
            <PanelLeftOpen className="size-4" />
          </Button>
        )}
        <h2 className="text-sm font-medium text-text-primary truncate flex-1">
          {data?.title
            || planningSummary
            || pendingUserMessage
            || (isLoading ? "" : "New Chat")}
        </h2>
        {/* In-folder picker */}
        {conversationId && (
          <MoveToFolderMenu conversationId={conversationId} currentFolderId={data?.folder_id ?? null}>
            <Button
              variant="ghost"
              size="sm"
              className="gap-1.5 text-text-muted"
              aria-label="Move chat to folder"
            >
              <Folder className="size-4" />
              <span className="max-w-[10rem] truncate text-xs">
                {folders?.find((f) => f.folder_id === data?.folder_id)?.name ?? "Add to folder"}
              </span>
            </Button>
          </MoveToFolderMenu>
        )}
        {/* Per-chat token usage — pulled right */}
        {chatTokens > 0 && (
          <span
            className="text-xs font-mono text-text-muted tabular-nums whitespace-nowrap"
            title={`${chatTokens.toLocaleString()} tokens in this chat`}
          >
            {formatTokens(chatTokens)} tokens
          </span>
        )}
        {/* Sources toggle */}
        {sourceCount > 0 && (
          <Button
            variant={sourcesOpen ? "outline" : "ghost"}
            size="icon-sm"
            onClick={onToggleSources}
            aria-label={sourcesOpen ? "Hide sources" : "Show sources"}
            className="relative"
          >
            <FileText className="size-4" />
            <Badge
              variant="secondary"
              className="absolute -top-1.5 -right-1.5 h-4 min-w-4 justify-center rounded-full px-1 text-[10px] leading-none"
            >
              {sourceCount}
            </Badge>
          </Button>
        )}
      </div>

      {/* Messages area */}
      <Conversation>
        <ConversationContent className="mx-auto w-full max-w-4xl">
          <MessageList
            messages={data?.messages ?? []}
            isLoading={isLoading}
            isStreaming={isStreaming}
            streamingContent={streamingContent}
            streamingSteps={streamingSteps}
            streamingSources={streamingSources}
            workspace={workspace}
            conversationId={conversationId}
            onFeedback={handleFeedback}
            surface={surface}
          />
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      {/* Input */}
      <ChatInput onSend={handleSend} disabled={streamingHere} onAbort={sendMessage.stop} modeLocked={!!forceMode} placeholder={placeholder} />
    </div>
  );
}
