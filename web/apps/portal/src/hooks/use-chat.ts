"use client";

import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query-keys";
import { authFetch, authFetchJson } from "@/lib/auth-fetch";
import { useChatStore } from "@/lib/stores/chat-store";
import { useAnalytics } from "@/hooks/use-analytics";
import type {
  Conversation,
  ChatMessage,
  AgentEvent,
  AgentStep,
  ContentBlock,
  GroundingStatus,
  SourceCitation,
  ThinkingBlock,
} from "@docu-store/types";

// ── Conversation CRUD ──────────────────────────────────────────────────────

export function useConversations() {
  return useQuery({
    queryKey: queryKeys.chat.list(),
    queryFn: () => authFetchJson<Conversation[]>("/chat"),
    staleTime: 30_000,
  });
}

export function useConversation(conversationId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.chat.detail(conversationId ?? ""),
    queryFn: () =>
      authFetchJson<Conversation & { messages: ChatMessage[] }>(
        `/chat/${conversationId}`,
      ),
    enabled: !!conversationId,
    staleTime: 10_000,
  });
}

export function useCreateConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (title?: string) => {
      const res = await authFetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title ?? null }),
      });
      if (!res.ok) throw new Error("Failed to create conversation");
      return res.json() as Promise<Conversation>;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.chat.list() });
    },
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (conversationId: string) => {
      const res = await authFetch(`/chat/${conversationId}`, {
        method: "DELETE",
      });
      if (!res.ok && res.status !== 404) throw new Error("Failed to delete");
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.chat.list() });
    },
  });
}

// ── Chat Feedback ─────────────────────────────────────────────────────────

export function useChatFeedback(conversationId: string | undefined) {
  const { trackEvent } = useAnalytics();

  return useMutation({
    mutationFn: async ({
      messageId,
      feedback,
      mode,
    }: {
      messageId: string;
      feedback: "positive" | "negative";
      mode: string;
    }) => {
      if (!conversationId) throw new Error("No conversation");
      const res = await authFetch(
        `/chat/${conversationId}/messages/${messageId}/feedback`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ feedback }),
        },
      );
      if (!res.ok) throw new Error("Failed to record feedback");
      trackEvent("chat_feedback", { message_id: messageId, feedback, mode });
    },
  });
}

// ── SSE Message Streaming ──────────────────────────────────────────────────

export function useSendMessage(conversationId: string | undefined) {
  const queryClient = useQueryClient();
  const store = useChatStore();
  const { trackEvent } = useAnalytics();
  const abortRef = useRef<AbortController | null>(null);

  const mutation = useMutation({
    mutationFn: async (message: string) => {
      if (!conversationId) throw new Error("No conversation selected");

      // Abort any in-flight stream before starting a new one
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const mode = store.chatMode;
      trackEvent("chat_message_sent", { mode, message_length: message.length });

      // Track follow-up depth: check if conversation already has messages
      const cached = queryClient.getQueryData<{ messages?: unknown[] }>(
        queryKeys.chat.detail(conversationId),
      );
      const existingCount = cached?.messages?.length ?? 0;
      if (existingCount > 0) {
        trackEvent("chat_follow_up_sent", {
          conversation_id: conversationId,
          message_count: existingCount + 1,
          mode,
        });
      }

      store.startStreaming(message);

      const streamStart = performance.now();
      const res = await authFetch(`/chat/${conversationId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, mode }),
        signal: controller.signal,
      });

      if (!res.ok) {
        store.finishStreaming();
        throw new Error(`Chat failed: ${res.statusText}`);
      }

      await processSSEStream(res, store, controller.signal, trackEvent);
      store.finishStreaming();

      const durationMs = Math.round(performance.now() - streamStart);
      trackEvent("chat_response_received", {
        duration_ms: durationMs,
        mode,
        step_count: store.streamingSteps.length,
      });
    },
    onSuccess: () => {
      // Refresh conversation detail to get persisted messages
      if (conversationId) {
        queryClient.invalidateQueries({
          queryKey: queryKeys.chat.detail(conversationId),
        });
        queryClient.invalidateQueries({ queryKey: queryKeys.chat.list() });
      }
    },
    onError: (error) => {
      // AbortError is expected on navigation — don't treat as a real error
      if (error instanceof DOMException && error.name === "AbortError") return;
      store.finishStreaming();
      trackEvent("chat_error", {
        mode: store.chatMode,
        error_type: error instanceof Error ? error.message.slice(0, 100) : "unknown",
      });
    },
  });

  /** Abort any in-flight stream. Call on unmount. */
  const abort = () => {
    abortRef.current?.abort();
    abortRef.current = null;
  };

  return { ...mutation, abort };
}

// ── SSE Parser ─────────────────────────────────────────────────────────────

interface ChatStoreActions {
  appendToken: (delta: string) => void;
  addStep: (step: AgentStep) => void;
  updateStep: (stepName: string, update: Partial<AgentStep>) => void;
  pushThinkingBlock: (block: ThinkingBlock) => void;
  addStructuredBlock: (block: ContentBlock) => void;
  setSources: (sources: SourceCitation[]) => void;
  setFinalSources: (sources: SourceCitation[]) => void;
  setGroundingResult: (result: GroundingStatus) => void;
  recordEvent: (event: AgentEvent) => void;
  setDoneEvent: (event: AgentEvent) => void;
}

type TrackEventFn = (name: string, data?: Record<string, string | number>) => void;

async function processSSEStream(
  response: Response,
  store: ChatStoreActions,
  signal: AbortSignal,
  trackEvent?: TrackEventFn,
): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) return;

  // Cancel the reader when the signal aborts
  const onAbort = () => reader.cancel();
  signal.addEventListener("abort", onAbort);

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      let currentEventType = "";

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          const jsonStr = line.slice(6);
          try {
            const event = JSON.parse(jsonStr) as AgentEvent;
            store.recordEvent(event);
            handleAgentEvent(event, currentEventType, store, trackEvent);
          } catch {
            // skip malformed events
          }
          currentEventType = "";
        }
      }
    }
  } finally {
    signal.removeEventListener("abort", onAbort);
    reader.releaseLock();
  }
}

function handleAgentEvent(
  event: AgentEvent,
  _sseType: string,
  store: ChatStoreActions,
  trackEvent?: TrackEventFn,
): void {
  switch (event.type) {
    case "step_started":
      store.addStep({
        step: event.step ?? "unknown",
        status: "started",
        started_at: null,
        completed_at: null,
        input_summary: null,
        output_summary: event.description ?? null,
        thinking_content: null,
      });
      break;

    case "step_completed":
      store.updateStep(event.step ?? "", {
        status: event.status === "started" ? "started" : "completed",
        output_summary: event.output ?? null,
        ...(event.thinking_content ? { thinking_content: event.thinking_content } : {}),
      });
      if (event.thinking_content) {
        store.pushThinkingBlock({
          label: event.thinking_label ?? `${event.step ?? "unknown"} thought`,
          step: event.step ?? "unknown",
          content: event.thinking_content,
        });
      }
      break;

    case "retrieval_results":
      if (event.sources) {
        store.setSources(event.sources);
      }
      break;

    case "token":
      if (event.delta) {
        store.appendToken(event.delta);
      }
      break;

    case "structured_block":
      if (event.block) {
        store.addStructuredBlock(event.block);
      }
      break;

    case "grounding_result":
      if (event.grounding_is_grounded != null && event.grounding_confidence != null) {
        store.setGroundingResult({
          is_grounded: event.grounding_is_grounded,
          confidence: event.grounding_confidence,
        });
      }
      break;

    case "done":
      if (event.sources) {
        // Set finalSources (cited-only) — distinct from streamingSources (all retrieved)
        store.setFinalSources(event.sources);
      }
      store.setDoneEvent(event);
      break;

    case "error":
      store.appendToken(
        `\n\n**Error:** ${event.error_message ?? "Unknown error"}`,
      );
      trackEvent?.("chat_stream_error", {
        error_type: (event.error_message ?? "unknown").slice(0, 100),
      });
      break;
  }
}
