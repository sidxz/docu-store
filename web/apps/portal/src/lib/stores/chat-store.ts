"use client";

import { create } from "zustand";
import type { AgentEvent, AgentStep, GroundingStatus, SourceCitation } from "@docu-store/types";

interface StepTiming {
  step: string;
  startedAt: number;
  completedAt: number | null;
  durationMs: number | null;
}

interface ChatState {
  // Streaming state
  isStreaming: boolean;
  streamingContent: string;
  streamingSteps: AgentStep[];
  streamingSources: SourceCitation[];  // all retrieved (from retrieval_results)
  finalSources: SourceCitation[] | null; // cited-only (from done event, null while streaming)

  // User message shown immediately while agent processes
  pendingUserMessage: string | null;

  // Grounding verification state
  groundingResult: GroundingStatus | null;

  // Message queued for send after navigation (new conversation flow)
  queuedMessage: string | null;

  // Citation highlight (click [N] in answer → flash in sources panel)
  highlightedCitation: number | null;
  // Which message's sources are shown in the panel (null = latest)
  activeSourcesMessageId: string | null;

  // Dev-mode diagnostics
  stepTimings: StepTiming[];
  rawEvents: AgentEvent[];
  doneEvent: AgentEvent | null;

  // Actions
  highlightCitation: (index: number, messageId?: string) => void;
  setActiveSourcesMessageId: (id: string | null) => void;
  setQueuedMessage: (msg: string | null) => void;
  startStreaming: (userMessage: string) => void;
  appendToken: (delta: string) => void;
  addStep: (step: AgentStep) => void;
  updateStep: (stepName: string, update: Partial<AgentStep>) => void;
  setSources: (sources: SourceCitation[]) => void;
  setFinalSources: (sources: SourceCitation[]) => void;
  setGroundingResult: (result: GroundingStatus) => void;
  recordEvent: (event: AgentEvent) => void;
  setDoneEvent: (event: AgentEvent) => void;
  finishStreaming: () => void;
  reset: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  isStreaming: false,
  streamingContent: "",
  streamingSteps: [],
  streamingSources: [],
  finalSources: null,
  pendingUserMessage: null,
  queuedMessage: null,
  groundingResult: null,
  highlightedCitation: null,
  activeSourcesMessageId: null,
  stepTimings: [],
  rawEvents: [],
  doneEvent: null,

  highlightCitation: (index, messageId) => {
    set({
      highlightedCitation: index,
      // Switch the sources panel to the clicked message's sources
      ...(messageId ? { activeSourcesMessageId: messageId } : {}),
    });
    setTimeout(() => set({ highlightedCitation: null }), 1500);
  },

  setActiveSourcesMessageId: (id) => set({ activeSourcesMessageId: id }),

  setQueuedMessage: (msg) => set({ queuedMessage: msg }),

  startStreaming: (userMessage) =>
    set({
      isStreaming: true,
      streamingContent: "",
      streamingSteps: [],
      streamingSources: [],
      finalSources: null,
      pendingUserMessage: userMessage,
      groundingResult: null,
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
        streamingSteps: state.streamingSteps.map((s) =>
          s.step === stepName ? { ...s, ...update } : s,
        ),
        stepTimings: state.stepTimings.map((t) =>
          t.step === stepName && t.completedAt === null
            ? { ...t, completedAt: now, durationMs: now - t.startedAt }
            : t,
        ),
      };
    }),

  setSources: (sources) => set({ streamingSources: sources }),

  setFinalSources: (sources) => set({ finalSources: sources }),

  setGroundingResult: (result) => set({ groundingResult: result }),

  recordEvent: (event) =>
    set((state) => ({
      rawEvents: [...state.rawEvents, event],
    })),

  setDoneEvent: (event) => set({ doneEvent: event }),

  finishStreaming: () => set({ isStreaming: false }),

  reset: () =>
    set({
      isStreaming: false,
      streamingContent: "",
      streamingSteps: [],
      streamingSources: [],
      finalSources: null,
      pendingUserMessage: null,
      groundingResult: null,
      highlightedCitation: null,
      activeSourcesMessageId: null,
      stepTimings: [],
      rawEvents: [],
      doneEvent: null,
    }),
}));
