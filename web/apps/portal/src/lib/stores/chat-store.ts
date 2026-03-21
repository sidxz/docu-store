"use client";

import { create } from "zustand";
import type { AgentEvent, AgentStep, SourceCitation } from "@docu-store/types";

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
  streamingSources: SourceCitation[];

  // Dev-mode diagnostics
  stepTimings: StepTiming[];
  rawEvents: AgentEvent[];
  doneEvent: AgentEvent | null;

  // Actions
  startStreaming: () => void;
  appendToken: (delta: string) => void;
  addStep: (step: AgentStep) => void;
  updateStep: (stepName: string, update: Partial<AgentStep>) => void;
  setSources: (sources: SourceCitation[]) => void;
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
  stepTimings: [],
  rawEvents: [],
  doneEvent: null,

  startStreaming: () =>
    set({
      isStreaming: true,
      streamingContent: "",
      streamingSteps: [],
      streamingSources: [],
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
      stepTimings: [],
      rawEvents: [],
      doneEvent: null,
    }),
}));
