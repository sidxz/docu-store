"use client";

import { useState } from "react";
import { Check, Loader2, AlertCircle, ListTree, ChevronRight, ChevronDown } from "lucide-react";
import type { AgentStep } from "@docu-store/types";

const STEP_LABELS: Record<string, string> = {
  // Quick Mode steps
  analysis: "Question Analysis",
  // Thinking Mode steps
  planning: "Query Planning",
  assembly: "Context Assembly",
  // Shared steps
  retrieval: "Document Retrieval",
  synthesis: "Answer Generation",
  verification: "Grounding Verification",
};

interface AgentStepIndicatorProps {
  step: AgentStep;
  durationMs: number | null;
  devMode: boolean;
}

export function AgentStepIndicator({ step, durationMs, devMode }: AgentStepIndicatorProps) {
  const [thinkingExpanded, setThinkingExpanded] = useState(false);
  const label = STEP_LABELS[step.step] ?? step.step;
  const hasThinking = !!step.thinking_content;

  return (
    <div className="flex items-start gap-2 text-xs">
      {step.status === "started" && (
        <Loader2 className="w-3.5 h-3.5 text-accent-text animate-spin flex-shrink-0 mt-0.5" />
      )}
      {step.status === "completed" && (
        <Check className="w-3.5 h-3.5 text-ds-success flex-shrink-0 mt-0.5" />
      )}
      {step.status === "failed" && (
        <AlertCircle className="w-3.5 h-3.5 text-ds-error flex-shrink-0 mt-0.5" />
      )}

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span
            className={`font-medium ${
              step.status === "started" ? "text-accent-text" : "text-text-secondary"
            }`}
          >
            {label}
          </span>
          {durationMs != null && (
            <span className="font-mono text-[10px] text-text-muted">
              {durationMs}ms
            </span>
          )}
          {hasThinking && (
            <button
              onClick={() => setThinkingExpanded(!thinkingExpanded)}
              className="flex items-center gap-0.5 text-[10px] text-accent-text/70 hover:text-accent-text transition-colors"
            >
              <ListTree className="w-3 h-3" />
              {thinkingExpanded ? (
                <ChevronDown className="w-3 h-3" />
              ) : (
                <ChevronRight className="w-3 h-3" />
              )}
            </button>
          )}
        </div>
        {step.output_summary && (
          <p className={`text-text-muted mt-0.5 ${devMode ? "whitespace-pre-wrap break-words" : "truncate"}`}>
            {step.output_summary}
          </p>
        )}
        {hasThinking && thinkingExpanded && (
          <div className="mt-1.5 space-y-2">
            {step.thinking_content!.split("\n\n---\n\n").map((block, i) => (
              <div
                key={i}
                className="rounded bg-surface-primary/50 border border-border-subtle px-2.5 py-2 text-[11px] text-text-muted whitespace-pre-wrap break-words leading-relaxed"
              >
                {block}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
