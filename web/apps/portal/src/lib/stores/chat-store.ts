"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { AgentEvent, AgentStep, ContentBlock, GroundingStatus, LiteratureHit, NerFilterTag, SourceCitation, ThinkingBlock } from "@docu-store/types";
import { trackEvent } from "@/lib/analytics";

interface StepTiming {
  step: string;
  startedAt: number;
  completedAt: number | null;
  durationMs: number | null;
}

export type ChatMode = "quick" | "thinking" | "deep_thinking";

export type ReasoningLevel = "off" | "low" | "medium" | "high";
export type ReasoningDefault = "inherit" | ReasoningLevel;
// Synthesis reasoning is mode-driven (composer toggle); retrieval/base are advanced knobs.
export type ReasoningDefaults = { retrieval: ReasoningDefault; base: ReasoningDefault };

// Reasoning is on by default in every mode. It used to be a per-mode default
// with quick opted out entirely; the split mostly meant the cheaper modes
// answered worse for no reason the user had chosen.
export const MODE_REASONING_DEFAULT: Record<ChatMode, boolean> = {
  quick: true,
  thinking: true,
  deep_thinking: true,
};

/** Effective reasoning on/off — mode default unless the user explicitly overrode it. */
export function isReasoningOn(mode: ChatMode, override: "on" | "off" | null): boolean {
  if (override !== null) return override === "on";
  return MODE_REASONING_DEFAULT[mode];
}

interface ChatState {
  // Pipeline mode
  chatMode: ChatMode;

  // Streaming state
  isStreaming: boolean;
  streamingContent: string;
  streamingSteps: AgentStep[];
  streamingSources: SourceCitation[];  // all retrieved (from retrieval_results)
  finalSources: SourceCitation[] | null; // cited-only (from done event, null while streaming)

  // User message shown immediately while agent processes
  pendingUserMessage: string | null;

  // Which conversation the streaming buffer belongs to — the store is global,
  // so optimistic bubbles must only render inside their own conversation.
  streamingConversationId: string | null;

  // Chronological thinking blocks (one per LLM thought)
  streamingThinkingBlocks: ThinkingBlock[];

  streamingReasoning: string;

  // Structured content blocks (molecules, tables, etc.)
  streamingStructuredBlocks: ContentBlock[];

  // Grounding verification state
  groundingResult: GroundingStatus | null;

  // Entity filters the planner ran retrieval with this turn (running list)
  queryFilters: NerFilterTag[];

  // Papers the last literature search returned, in Europe PMC's relevance order.
  // Never re-sorted: ranking these by whether they can be ingested would bury
  // the paywalled med-chem papers, which are usually the relevant ones.
  literatureResults: LiteratureHit[];

  // Message queued for send after navigation (new conversation flow)
  queuedMessage: string | null;

  // Conversations whose answer completed while the user wasn't looking.
  // Cross-conversation state: NOT part of the streaming slot, survives
  // reset(), and persists across reloads (see partialize).
  unreadAnswers: string[];

  // Citation highlight (click [N] in answer → flash in sources panel)
  highlightedCitation: number | null;
  // Which message's sources are shown in the panel (null = latest)
  activeSourcesMessageId: string | null;

  // Dev-mode diagnostics
  stepTimings: StepTiming[];
  rawEvents: AgentEvent[];
  doneEvent: AgentEvent | null;

  // Reasoning
  reasoningDefaults: ReasoningDefaults;
  synthesisOverride: "on" | "off" | null;
  setReasoningDefault: (lane: keyof ReasoningDefaults, level: ReasoningDefault) => void;
  setSynthesisOverride: (v: "on" | "off" | null) => void;
  effectiveReasoning: () => Partial<Record<"synthesis" | "retrieval" | "base", ReasoningLevel>>;

  // Actions
  setChatMode: (mode: ChatMode) => void;
  highlightCitation: (index: number, messageId?: string) => void;
  setActiveSourcesMessageId: (id: string | null) => void;
  setQueuedMessage: (msg: string | null) => void;
  markUnread: (conversationId: string) => void;
  clearUnread: (conversationId: string) => void;
  startStreaming: (userMessage: string, conversationId: string | null) => void;
  resumeStreaming: (conversationId: string) => void;
  appendToken: (delta: string) => void;
  addStep: (step: AgentStep) => void;
  updateStep: (stepName: string, update: Partial<AgentStep>) => void;
  pushThinkingBlock: (block: ThinkingBlock) => void;
  appendReasoning: (delta: string) => void;
  addStructuredBlock: (block: ContentBlock) => void;
  setSources: (sources: SourceCitation[]) => void;
  setFinalSources: (sources: SourceCitation[]) => void;
  setGroundingResult: (result: GroundingStatus) => void;
  setQueryFilters: (filters: NerFilterTag[]) => void;
  setLiteratureResults: (results: LiteratureHit[]) => void;
  recordEvent: (event: AgentEvent) => void;
  setDoneEvent: (event: AgentEvent) => void;
  finishStreaming: () => void;
  reset: () => void;
}

let highlightTimer: ReturnType<typeof setTimeout> | null = null;

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
  chatMode: "thinking" as ChatMode,
  isStreaming: false,
  streamingContent: "",
  streamingSteps: [],
  streamingSources: [],
  finalSources: null,
  pendingUserMessage: null,
  streamingConversationId: null,
  queuedMessage: null,
  unreadAnswers: [],
  streamingThinkingBlocks: [],
  streamingReasoning: "",
  streamingStructuredBlocks: [],
  groundingResult: null,
  queryFilters: [],
  literatureResults: [],
  highlightedCitation: null,
  activeSourcesMessageId: null,
  stepTimings: [],
  rawEvents: [],
  doneEvent: null,

  reasoningDefaults: { retrieval: "inherit", base: "inherit" },
  synthesisOverride: null,

  setReasoningDefault: (lane, level) =>
    set((state) => ({ reasoningDefaults: { ...state.reasoningDefaults, [lane]: level } })),
  setSynthesisOverride: (v) => set({ synthesisOverride: v }),
  effectiveReasoning: () => {
    const { chatMode, reasoningDefaults, synthesisOverride } = get();
    const result: Partial<Record<"synthesis" | "retrieval" | "base", ReasoningLevel>> = {};
    // retrieval/base: advanced knobs — omit "inherit" so backend env defaults win.
    if (reasoningDefaults.retrieval !== "inherit") result.retrieval = reasoningDefaults.retrieval;
    if (reasoningDefaults.base !== "inherit") result.base = reasoningDefaults.base;
    // synthesis: authoritative — always explicit so the UI is the source of truth
    // (never silently inherits the server env default like the old omit behavior did).
    result.synthesis = isReasoningOn(chatMode, synthesisOverride) ? "medium" : "off";
    return result;
  },

  setChatMode: (mode) => {
    trackEvent("chat_mode_changed", { mode });
    // Reset the per-message reasoning toggle so it follows the new mode's default.
    set({ chatMode: mode, synthesisOverride: null });
  },

  highlightCitation: (index, messageId) => {
    if (highlightTimer) clearTimeout(highlightTimer);
    set({
      highlightedCitation: index,
      // Switch the sources panel to the clicked message's sources
      ...(messageId ? { activeSourcesMessageId: messageId } : {}),
    });
    highlightTimer = setTimeout(() => {
      highlightTimer = null;
      set({ highlightedCitation: null });
    }, 1500);
  },

  setActiveSourcesMessageId: (id) => set({ activeSourcesMessageId: id }),

  setQueuedMessage: (msg) => set({ queuedMessage: msg }),

  markUnread: (conversationId) =>
    set((state) =>
      state.unreadAnswers.includes(conversationId)
        ? state
        : { unreadAnswers: [...state.unreadAnswers, conversationId] },
    ),

  clearUnread: (conversationId) =>
    set((state) =>
      state.unreadAnswers.includes(conversationId)
        ? { unreadAnswers: state.unreadAnswers.filter((id) => id !== conversationId) }
        : state,
    ),

  startStreaming: (userMessage, conversationId) =>
    set({
      isStreaming: true,
      streamingContent: "",
      streamingSteps: [],
      streamingSources: [],
      finalSources: null,
      pendingUserMessage: userMessage,
      streamingConversationId: conversationId,
      streamingThinkingBlocks: [],
      streamingReasoning: "",
      streamingStructuredBlocks: [],
      groundingResult: null,
      queryFilters: [],
      literatureResults: [],
      stepTimings: [],
      rawEvents: [],
      doneEvent: null,
    }),

  resumeStreaming: (conversationId) =>
    set({
      isStreaming: true,
      streamingContent: "",
      streamingSteps: [],
      streamingSources: [],
      finalSources: null,
      pendingUserMessage: null,
      streamingConversationId: conversationId,
      streamingThinkingBlocks: [],
      streamingReasoning: "",
      streamingStructuredBlocks: [],
      groundingResult: null,
      queryFilters: [],
      literatureResults: [],
      stepTimings: [],
      rawEvents: [],
      doneEvent: null,
    }),

  appendToken: (delta) =>
    set((state) => ({
      streamingContent: state.streamingContent + delta,
    })),

  addStep: (step) =>
    set((state) => ({
      streamingSteps: [...state.streamingSteps, step],
      stepTimings: [
        ...state.stepTimings,
        { step: step.step, startedAt: Date.now(), completedAt: null, durationMs: null },
      ],
    })),

  updateStep: (stepName, update) =>
    set((state) => {
      const now = Date.now();
      return {
        streamingSteps: state.streamingSteps.map((s) => {
          if (s.step !== stepName) return s;
          const merged = { ...s, ...update };
          // Accumulate thinking_content instead of overwriting
          if (update.thinking_content && s.thinking_content) {
            merged.thinking_content = s.thinking_content + "\n\n---\n\n" + update.thinking_content;
          }
          return merged;
        }),
        stepTimings: state.stepTimings.map((t) =>
          t.step === stepName && t.completedAt === null
            ? { ...t, completedAt: now, durationMs: now - t.startedAt }
            : t,
        ),
      };
    }),

  pushThinkingBlock: (block) =>
    set((state) => ({
      streamingThinkingBlocks: [...state.streamingThinkingBlocks, block],
    })),

  appendReasoning: (delta) =>
    set((state) => ({
      streamingReasoning: state.streamingReasoning + delta,
    })),

  addStructuredBlock: (block) =>
    set((state) => ({
      streamingStructuredBlocks: [...state.streamingStructuredBlocks, block],
    })),

  setSources: (sources) => set({ streamingSources: sources }),

  setFinalSources: (sources) => set({ finalSources: sources }),

  setGroundingResult: (result) => set({ groundingResult: result }),

  recordEvent: (event) =>
    set((state) => ({
      rawEvents: [...state.rawEvents, event],
    })),

  setQueryFilters: (filters) => set({ queryFilters: filters }),

  // Accumulate across the turn rather than replace. The agent searches several
  // times per question, and citations span all of those searches -- keeping only
  // the last one leaves most of the papers the answer used missing from the
  // panel, which is exactly where the reader goes to act on them. Deduped on
  // identity, first sighting wins, so relevance order is preserved.
  setLiteratureResults: (results) =>
    set((state) => {
      const seen = new Set(state.literatureResults.map((r) => `${r.source}-${r.external_id}`));
      const fresh = results.filter((r) => !seen.has(`${r.source}-${r.external_id}`));
      return fresh.length ? { literatureResults: [...state.literatureResults, ...fresh] } : {};
    }),

  setDoneEvent: (event) => set({ doneEvent: event }),

  finishStreaming: () =>
    set((state) => {
      const doneEvent = state.doneEvent;
      if (doneEvent) {
        const totalDuration =
          (doneEvent as unknown as Record<string, unknown>).duration_ms as number | undefined;
        const firstStep = state.stepTimings[0];
        const ttft = firstStep?.durationMs ?? undefined;
        trackEvent("chat_pipeline_completed", {
          total_duration_ms: totalDuration ?? 0,
          time_to_first_step_ms: ttft ?? 0,
          mode: state.chatMode,
          step_count: state.streamingSteps.length,
        });
      }
      return { isStreaming: false };
    }),

  reset: () =>
    set({
      isStreaming: false,
      streamingContent: "",
      streamingSteps: [],
      streamingSources: [],
      finalSources: null,
      pendingUserMessage: null,
      streamingConversationId: null,
      streamingThinkingBlocks: [],
      streamingReasoning: "",
      streamingStructuredBlocks: [],
      groundingResult: null,
      queryFilters: [],
      literatureResults: [],
      highlightedCitation: null,
      activeSourcesMessageId: null,
      stepTimings: [],
      rawEvents: [],
      doneEvent: null,
    }),
    }),
    {
      name: "docu-store-chat-reasoning",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({
        reasoningDefaults: s.reasoningDefaults,
        unreadAnswers: s.unreadAnswers,
      }),
      skipHydration: true,
    },
  ),
);
