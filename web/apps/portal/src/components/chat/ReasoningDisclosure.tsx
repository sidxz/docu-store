"use client";

import { useState } from "react";
import { Brain, ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { MarkdownRenderer } from "./MarkdownRenderer";

interface ReasoningDisclosureProps {
  reasoning: string;
  isStreaming?: boolean;
}

export function ReasoningDisclosure({ reasoning, isStreaming }: ReasoningDisclosureProps) {
  // Open while the model is actively reasoning; collapsed once the answer is ready.
  const [open, setOpen] = useState(true);
  if (!reasoning) return null;

  return (
    <div className="mb-2 rounded-lg border border-border-subtle bg-surface-elevated/60">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary"
        aria-expanded={open}
      >
        <Brain className="h-3.5 w-3.5 text-feature-search" />
        <span className="font-medium">Reasoning</span>
        {isStreaming && <Loader2 className="h-3 w-3 animate-spin text-text-muted" />}
        <span className="ml-auto">
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </span>
      </button>
      {open && (
        <div className="border-t border-border-subtle px-3 py-2 prose prose-sm dark:prose-invert max-w-none text-text-secondary">
          <MarkdownRenderer content={reasoning} />
        </div>
      )}
    </div>
  );
}
