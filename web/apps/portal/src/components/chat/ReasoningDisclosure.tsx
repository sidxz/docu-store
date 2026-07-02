"use client";

import { useState } from "react";
import { Reasoning, ReasoningTrigger } from "@/components/ai-elements/reasoning";
import { CollapsibleContent } from "@/components/ui/collapsible";
import { MarkdownRenderer } from "./MarkdownRenderer";

interface ReasoningDisclosureProps {
  reasoning: string;
  isStreaming?: boolean;
}

export function ReasoningDisclosure({ reasoning, isStreaming }: ReasoningDisclosureProps) {
  // Mount-time snapshot, NOT a live alias: the vendored auto-close effect
  // gates on `defaultOpen && !isStreaming`, so `defaultOpen={isStreaming}`
  // would flip both false in the same render when streaming ends and kill
  // the auto-close. Snapshot keeps historical messages closed (no flash)
  // while live-streamed ones still open and auto-close.
  const [initialOpen] = useState(() => !!isStreaming);

  if (!reasoning) return null;

  return (
    <Reasoning
      isStreaming={isStreaming}
      defaultOpen={initialOpen}
      className="mb-2 rounded-lg border border-border-subtle bg-surface-elevated/60 px-3 py-1.5"
    >
      <ReasoningTrigger className="text-xs" />
      {/* ai-elements ReasoningContent forces its markdown through a private
          Streamdown instance (typed `children: string`), which lacks this
          app's custom table/code/link/citation renderers (see
          MarkdownRenderer.tsx). Use the plain CollapsibleContent primitive
          instead — same Radix root, same open/close animation classes as
          ReasoningContent — and keep MarkdownRenderer as the content. */}
      <CollapsibleContent className="mt-2 border-t border-border-subtle pt-2 text-xs text-text-secondary outline-none data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-top-2 data-[state=closed]:animate-out data-[state=open]:slide-in-from-top-2 data-[state=open]:animate-in">
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <MarkdownRenderer content={reasoning} />
        </div>
      </CollapsibleContent>
    </Reasoning>
  );
}
