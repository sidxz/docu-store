"use client";

import { useState, type ComponentProps } from "react";
import { AlertCircle, Check, ChevronDown, ChevronRight, ListTree, Loader2, type LucideIcon } from "lucide-react";
import type { AgentStep } from "@docu-store/types";
import { cn } from "@/lib/utils";
import { ChainOfThoughtStep } from "@/components/ai-elements/chain-of-thought";

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

// ponytail: ChainOfThoughtStep's `icon` prop is typed as lucide-react's
// `LucideIcon` (a forwardRef component) and renders it as `<Icon
// className="size-4" />` with no way to layer on extra classes (spin,
// status color) from the outside. Wrap+cast so each status keeps its
// original icon color (and the "started" spinner), same trick used for
// checkpoint.tsx's LucideProps mismatch in Task 2.
function coloredIcon(Icon: LucideIcon, extraClassName: string): LucideIcon {
  const Wrapped = (props: ComponentProps<LucideIcon>) => (
    <Icon {...props} className={cn(props.className, extraClassName)} />
  );
  return Wrapped as unknown as LucideIcon;
}

const STATUS_ICON: Record<AgentStep["status"], LucideIcon> = {
  started: coloredIcon(Loader2, "text-accent-text animate-spin"),
  completed: coloredIcon(Check, "text-ds-success"),
  failed: coloredIcon(AlertCircle, "text-ds-error"),
};

const STATUS_STEP: Record<AgentStep["status"], "pending" | "active" | "complete"> = {
  started: "active",
  completed: "complete",
  failed: "complete",
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
    <ChainOfThoughtStep
      icon={STATUS_ICON[step.status]}
      status={STATUS_STEP[step.status]}
      className={cn(step.status === "failed" && "text-ds-error")}
      label={
        <div className="flex items-center gap-2">
          <span className="font-medium">{label}</span>
          {durationMs != null && (
            <span className="font-mono text-[10px] text-text-muted">{durationMs}ms</span>
          )}
          {hasThinking && (
            <button
              type="button"
              onClick={() => setThinkingExpanded((v) => !v)}
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
      }
    >
      {step.output_summary && (
        <p className={`text-text-muted ${devMode ? "whitespace-pre-wrap break-words" : "truncate"}`}>
          {step.output_summary}
        </p>
      )}
      {hasThinking && thinkingExpanded && (
        <div className="space-y-2">
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
    </ChainOfThoughtStep>
  );
}
