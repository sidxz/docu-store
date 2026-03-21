"use client";

import { Check, Loader2, AlertCircle } from "lucide-react";
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
  const label = STEP_LABELS[step.step] ?? step.step;

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
        </div>
        {step.output_summary && (
          <p className={`text-text-muted mt-0.5 ${devMode ? "whitespace-pre-wrap break-words" : "truncate"}`}>
            {step.output_summary}
          </p>
        )}
      </div>
    </div>
  );
}
