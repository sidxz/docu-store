"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query-keys";
import { authFetch, authFetchJson } from "@/lib/auth-fetch";
import { useChatStore } from "@/lib/stores/chat-store";
import type {
  Conversation,
  ChatMessage,
  AgentEvent,
  AgentStep,
  SourceCitation,
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
      authFetchJson<{ conversation: Conversation; messages: ChatMessage[] }>(
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

// ── SSE Message Streaming ──────────────────────────────────────────────────

export function useSendMessage(conversationId: string | undefined) {
  const queryClient = useQueryClient();
  const store = useChatStore();

  return useMutation({
    mutationFn: async (message: string) => {
      if (!conversationId) throw new Error("No conversation selected");

      store.startStreaming();

      const res = await authFetch(`/chat/${conversationId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });

      if (!res.ok) {
        store.finishStreaming();
        throw new Error(`Chat failed: ${res.statusText}`);
      }

      await processSSEStream(res, store);
      store.finishStreaming();
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
    onError: () => {
      store.finishStreaming();
    },
  });
}

// ── SSE Parser ─────────────────────────────────────────────────────────────

interface ChatStoreActions {
  appendToken: (delta: string) => void;
  addStep: (step: AgentStep) => void;
  updateStep: (stepName: string, update: Partial<AgentStep>) => void;
  setSources: (sources: SourceCitation[]) => void;
  recordEvent: (event: AgentEvent) => void;
  setDoneEvent: (event: AgentEvent) => void;
}

async function processSSEStream(
  response: Response,
  store: ChatStoreActions,
): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";

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
          handleAgentEvent(event, currentEventType, store);
        } catch {
          // skip malformed events
        }
        currentEventType = "";
      }
    }
  }
}

function handleAgentEvent(
  event: AgentEvent,
  _sseType: string,
  store: ChatStoreActions,
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
      });
      break;

    case "step_completed":
      store.updateStep(event.step ?? "", {
        status: "completed",
        output_summary: event.output ?? null,
      });
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

    case "done":
      if (event.sources) {
        store.setSources(event.sources);
      }
      store.setDoneEvent(event);
      break;

    case "error":
      store.appendToken(
        `\n\n**Error:** ${event.error_message ?? "Unknown error"}`,
      );
      break;
  }
}
