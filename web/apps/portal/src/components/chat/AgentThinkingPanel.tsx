"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Clock, Brain, Search, Target, FlaskConical, Sparkles } from "lucide-react";
import type { AgentTrace, AgentStep, ThinkingBlock } from "@docu-store/types";
import { useDevModeStore } from "@/lib/stores/dev-mode-store";
import { useChatStore } from "@/lib/stores/chat-store";
import { AgentStepIndicator } from "./AgentStepIndicator";
import { MarkdownRenderer } from "./MarkdownRenderer";

interface AgentThinkingPanelProps {
  trace: AgentTrace;
  isStreaming?: boolean;
}

function getStepDuration(step: AgentStep, streamingTimings: { step: string; durationMs: number | null }[]): number | null {
  // Prefer server-side timestamps (persisted messages)
  if (step.started_at && step.completed_at) {
    return new Date(step.completed_at).getTime() - new Date(step.started_at).getTime();
  }
  // Fall back to client-side timing (streaming)
  const timing = streamingTimings.find((t) => t.step === step.step);
  return timing?.durationMs ?? null;
}

export function AgentThinkingPanel({ trace, isStreaming }: AgentThinkingPanelProps) {
  const [expanded, setExpanded] = useState(true);
  const userCollapsed = useRef(false);
  const prevStreaming = useRef(isStreaming);
  const devMode = useDevModeStore((s) => s.enabled);
  const { stepTimings, doneEvent, rawEvents, streamingThinkingBlocks } = useChatStore();

  // Auto-collapse when streaming finishes, unless user already collapsed
  useEffect(() => {
    if (prevStreaming.current && !isStreaming && !userCollapsed.current) {
      setExpanded(false);
    }
    prevStreaming.current = isStreaming;
  }, [isStreaming]);

  const steps = trace.steps;
  if (!steps.length) return null;

  const completedCount = steps.filter((s) => s.status === "completed").length;
  const totalMs = trace.total_duration_ms;
  const label = isStreaming
    ? `Thinking (${completedCount}/${steps.length} steps)...`
    : `Thinking history (${completedCount} steps${totalMs ? `, ${(totalMs / 1000).toFixed(1)}s` : ""})`;

  // Resolve thinking blocks: streaming → persisted → fallback from step thinking_content
  const thinkingBlocks = isStreaming
    ? streamingThinkingBlocks
    : resolveThinkingBlocks(trace);

  return (
    <div className="mb-2">
      <button
        onClick={() => {
          const next = !expanded;
          setExpanded(next);
          if (!next) userCollapsed.current = true;
        }}
        className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary transition-colors"
      >
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5" />
        )}
        {isStreaming ? (
          <span className="relative flex h-3 w-3">
            <span className="absolute inline-flex h-full w-full rounded-full bg-accent-text/40 animate-ping" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-accent-text" />
          </span>
        ) : (
          <Clock className="w-3 h-3" />
        )}
        <span>{label}</span>
      </button>

      {expanded && (
        <div className="mt-1.5 ml-2 pl-3 border-l-2 border-border-subtle space-y-1.5">
          {steps.map((step, i) => (
            <AgentStepIndicator
              key={`${step.step}-${i}`}
              step={step}
              durationMs={getStepDuration(step, stepTimings)}
              devMode={devMode}
            />
          ))}
        </div>
      )}

      {/* Chronological thinking log — all LLM thoughts across steps */}
      {expanded && thinkingBlocks.length > 0 && (
        <ThinkingLog blocks={thinkingBlocks} />
      )}

      {/* Dev-mode: pipeline summary — works for both streaming and persisted */}
      {devMode && expanded && (
        <DevPipelineSummary
          trace={trace}
          steps={steps}
          stepTimings={stepTimings}
          doneEvent={doneEvent}
          rawEvents={rawEvents}
          isStreaming={isStreaming}
        />
      )}
    </div>
  );
}

// --- Thinking Log ---

const STEP_COLORS: Record<string, string> = {
  planning: "bg-blue-500/15 text-blue-400",
  retrieval: "bg-amber-500/15 text-amber-400",
  synthesis: "bg-purple-500/15 text-purple-400",
  verification: "bg-emerald-500/15 text-emerald-400",
};

function resolveThinkingBlocks(trace: AgentTrace): ThinkingBlock[] {
  // Use structured thinking_blocks if available (new messages)
  if (trace.thinking_blocks && trace.thinking_blocks.length > 0) {
    return trace.thinking_blocks;
  }
  // Fallback: extract from step thinking_content (old messages)
  const blocks: ThinkingBlock[] = [];
  for (const step of trace.steps) {
    if (!step.thinking_content) continue;
    const parts = step.thinking_content.split("\n\n---\n\n");
    for (let i = 0; i < parts.length; i++) {
      blocks.push({
        label: parts.length > 1 ? `${step.step} thought ${i + 1}` : `${step.step} thought`,
        step: step.step,
        content: parts[i],
      });
    }
  }
  return blocks;
}

// --- Query Plan Card ---

interface QueryPlan {
  query_type?: string;
  reformulated_query?: string;
  sub_queries?: string[];
  entities?: string[];
  smiles_detected?: string[];
  search_strategy?: string;
  hyde_hypothesis?: string | null;
  confidence?: number;
  summary?: string;
}

/** Try to extract JSON from a thinking block (may be wrapped in ```json ... ```) */
function tryParseQueryPlan(content: string): QueryPlan | null {
  const jsonMatch = content.match(/```json\s*\n([\s\S]*?)\n```/);
  const jsonStr = jsonMatch ? jsonMatch[1] : content.trim();
  try {
    const parsed = JSON.parse(jsonStr);
    if (parsed && typeof parsed === "object" && ("query_type" in parsed || "reformulated_query" in parsed)) {
      return parsed as QueryPlan;
    }
  } catch {
    // Not valid JSON
  }
  return null;
}

const QUERY_TYPE_STYLES: Record<string, string> = {
  factual: "bg-blue-500/15 text-blue-400",
  comparative: "bg-purple-500/15 text-purple-400",
  exploratory: "bg-amber-500/15 text-amber-400",
  compound: "bg-emerald-500/15 text-emerald-400",
  follow_up: "bg-zinc-500/15 text-zinc-400",
};

const STRATEGY_ICONS: Record<string, typeof Search> = {
  hierarchical: Search,
  summary: Sparkles,
  compound: FlaskConical,
};

function QueryPlanCard({ plan }: { plan: QueryPlan }) {
  const typeStyle = QUERY_TYPE_STYLES[plan.query_type ?? ""] ?? "bg-zinc-500/15 text-zinc-400";
  const StrategyIcon = STRATEGY_ICONS[plan.search_strategy ?? ""] ?? Search;

  return (
    <div className="rounded bg-surface-primary/50 border border-border-subtle px-2.5 py-2 text-[11px] space-y-1.5">
      {/* Top row: type + strategy + confidence */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${typeStyle}`}>
          {plan.query_type ?? "unknown"}
        </span>
        <span className="flex items-center gap-1 text-text-muted">
          <StrategyIcon className="w-3 h-3" />
          <span>{plan.search_strategy ?? "—"}</span>
        </span>
        {plan.confidence != null && (
          <span className="text-text-muted">
            confidence: <span className={plan.confidence >= 0.8 ? "text-ds-success" : "text-ds-warning"}>{Math.round(plan.confidence * 100)}%</span>
          </span>
        )}
      </div>

      {/* Reformulated query */}
      {plan.reformulated_query && (
        <div className="text-text-secondary leading-relaxed">
          <span className="text-text-muted">Query: </span>
          {plan.reformulated_query}
        </div>
      )}

      {/* Entities */}
      {plan.entities && plan.entities.length > 0 && (
        <div className="flex items-center gap-1 flex-wrap">
          <Target className="w-3 h-3 text-text-muted shrink-0" />
          {plan.entities.map((e, i) => (
            <span key={i} className="rounded bg-surface-elevated px-1.5 py-0.5 text-[10px] text-text-secondary">
              {e}
            </span>
          ))}
        </div>
      )}

      {/* Sub-queries */}
      {plan.sub_queries && plan.sub_queries.length > 0 && (
        <div className="text-text-muted">
          <span>Sub-queries: </span>
          {plan.sub_queries.map((q, i) => (
            <span key={i} className="text-text-secondary">{i > 0 ? " · " : ""}{q}</span>
          ))}
        </div>
      )}

      {/* Summary */}
      {plan.summary && (
        <div className="text-text-muted leading-relaxed italic">
          {plan.summary}
        </div>
      )}
    </div>
  );
}

function ThinkingLog({ blocks }: { blocks: ThinkingBlock[] }) {
  const [logExpanded, setLogExpanded] = useState(true);

  return (
    <div className="mt-2 ml-2">
      <button
        onClick={() => setLogExpanded(!logExpanded)}
        className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary transition-colors mb-1.5"
      >
        <Brain className="w-3 h-3" />
        {logExpanded ? (
          <ChevronDown className="w-3 h-3" />
        ) : (
          <ChevronRight className="w-3 h-3" />
        )}
        <span>Agent thoughts ({blocks.length})</span>
      </button>

      {logExpanded && (
        <div className="pl-3 border-l-2 border-border-subtle space-y-2">
          {blocks.map((block, i) => {
            const colorClass = STEP_COLORS[block.step] ?? "bg-zinc-500/15 text-zinc-400";
            const queryPlan = block.step === "planning" ? tryParseQueryPlan(block.content) : null;
            return (
              <div key={i} className="space-y-1">
                <div className="flex items-center gap-1.5">
                  <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${colorClass}`}>
                    {block.step}
                  </span>
                  <span className="text-[11px] text-text-secondary font-medium">{block.label}</span>
                </div>
                {queryPlan ? (
                  <QueryPlanCard plan={queryPlan} />
                ) : (
                  <div className="rounded bg-surface-primary/50 border border-border-subtle px-2.5 py-2 text-[11px] text-text-muted break-words leading-relaxed prose prose-invert prose-xs max-w-none">
                    <MarkdownRenderer content={block.content} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// --- Dev Pipeline Summary ---

function DevPipelineSummary({
  trace,
  steps,
  stepTimings,
  doneEvent,
  rawEvents,
  isStreaming,
}: {
  trace: AgentTrace;
  steps: AgentStep[];
  stepTimings: { step: string; durationMs: number | null }[];
  doneEvent: { duration_ms?: number | null; total_tokens?: number | null } | null;
  rawEvents: unknown[];
  isStreaming?: boolean;
}) {
  // Use server-side total or client-side doneEvent
  const totalMs = trace.total_duration_ms ?? doneEvent?.duration_ms;
  const totalTokens = doneEvent?.total_tokens;

  // Compute step durations from either source
  const durations = steps.map((s) => ({
    step: s.step,
    ms: getStepDurationInner(s, stepTimings),
    status: s.status,
  }));

  if (!totalMs && !isStreaming && durations.every((d) => d.ms === null)) return null;

  return (
    <div className="mt-2 ml-2 rounded bg-surface-elevated px-2 py-1.5 text-[10px] font-mono text-text-muted space-y-0.5">
      <div className="flex flex-wrap gap-x-3">
        <span className="font-semibold text-text-secondary">Pipeline</span>
        {totalMs != null && (
          <span>total: <span className="text-accent-text">{totalMs}ms</span></span>
        )}
        {totalTokens != null && (
          <span>tokens: <span className="text-feature-search">{totalTokens}</span></span>
        )}
        {trace.retry_count > 0 && (
          <span className="text-ds-warning">retries: {trace.retry_count}</span>
        )}
        {isStreaming && rawEvents.length > 0 && (
          <span>events: <span className="text-ds-success">{rawEvents.length}</span></span>
        )}
      </div>
      <div className="flex flex-wrap gap-x-3">
        {durations.map((d) => (
          <span key={d.step}>
            {d.step}:{" "}
            <span className={
              d.status === "completed"
                ? "text-ds-success"
                : d.status === "started"
                  ? "text-ds-warning"
                  : "text-ds-error"
            }>
              {d.ms != null ? `${d.ms}ms` : d.status === "started" ? "running..." : "—"}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

function getStepDurationInner(step: AgentStep, streamingTimings: { step: string; durationMs: number | null }[]): number | null {
  if (step.started_at && step.completed_at) {
    return new Date(step.completed_at).getTime() - new Date(step.started_at).getTime();
  }
  const timing = streamingTimings.find((t) => t.step === step.step);
  return timing?.durationMs ?? null;
}
