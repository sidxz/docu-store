"use client";

import type { ReactNode } from "react";
import { Streamdown } from "streamdown";
import { createMathPlugin } from "@streamdown/math";
import "katex/dist/katex.min.css";
import { useChatStore } from "@/lib/stores/chat-store";
import { useAnalytics } from "@/hooks/use-analytics";

// Render LaTeX. singleDollarTextMath: the model emits single-$ inline math
// ($\text{IC}_{50}$, $37\mu\text{M}$) — the plugin defaults this to false,
// which would leave that LaTeX as raw source. Created once at module scope.
const mathPlugin = createMathPlugin({ singleDollarTextMath: true });

interface MarkdownRendererProps {
  content: string;
  messageId?: string;
}

export function MarkdownRenderer({ content, messageId }: MarkdownRendererProps) {
  const highlightCitation = useChatStore((s) => s.highlightCitation);
  const { trackEvent } = useAnalytics();

  if (!content) return null;

  // Tables/code/links use Streamdown's built-in styling (sourced in
  // globals.css). Only citation [N] parsing is app-specific.
  return (
    <Streamdown
      plugins={{ math: mathPlugin }}
      components={{
        p: ({ children }) => <p>{styleCitations(children, messageId, highlightCitation, trackEvent)}</p>,
        // className mirrors Streamdown's own li default, which this override replaces
        li: ({ children }) => <li className="py-1 [&>p]:inline">{styleCitations(children, messageId, highlightCitation, trackEvent)}</li>,
      }}
    >
      {content}
    </Streamdown>
  );
}

const CITATION_PATTERN = /\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]/g;

type HighlightFn = (index: number, messageId?: string) => void;
type TrackFn = (name: string, data?: Record<string, string | number>) => void;

function styleCitations(children: ReactNode, messageId: string | undefined, onHighlight: HighlightFn, trackEvent: TrackFn): ReactNode {
  if (!children) return children;

  if (typeof children === "string") {
    return replaceCitationsInText(children, messageId, onHighlight, trackEvent);
  }

  if (Array.isArray(children)) {
    return children.map((child, i) => {
      if (typeof child === "string") {
        return <span key={i}>{replaceCitationsInText(child, messageId, onHighlight, trackEvent)}</span>;
      }
      return child;
    });
  }

  return children;
}

function replaceCitationsInText(text: string, messageId: string | undefined, onHighlight: HighlightFn, trackEvent: TrackFn): ReactNode {
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  CITATION_PATTERN.lastIndex = 0;
  while ((match = CITATION_PATTERN.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const nums = match[1].split(",").map((s) => s.trim());
    for (const num of nums) {
      const citationNum = parseInt(num, 10);
      parts.push(
        <button
          key={`c${match.index}-${num}`}
          type="button"
          onClick={() => {
            onHighlight(citationNum, messageId);
            trackEvent("citation_clicked", { citation_index: citationNum, source: "inline" });
          }}
          className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1 mx-0.5 rounded bg-accent-light text-accent-text text-[10px] font-semibold align-baseline cursor-pointer hover:bg-accent-muted transition-colors"
        >
          {num}
        </button>,
      );
    }
    lastIndex = match.index + match[0].length;
  }

  if (parts.length === 0) return text;
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
}
