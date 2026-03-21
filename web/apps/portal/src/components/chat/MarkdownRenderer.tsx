"use client";

import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useChatStore } from "@/lib/stores/chat-store";

interface MarkdownRendererProps {
  content: string;
  messageId?: string;
}

export function MarkdownRenderer({ content, messageId }: MarkdownRendererProps) {
  if (!content) return null;

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        table: ({ children }) => (
          <div className="overflow-x-auto my-3">
            <table className="w-full text-sm border-collapse border border-border-default">
              {children}
            </table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-surface-elevated">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-3 py-2 text-left font-semibold border border-border-default">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-3 py-2 border border-border-default">
            {children}
          </td>
        ),
        code: ({ className, children, ...props }) => {
          const isInline = !className;
          if (isInline) {
            return (
              <code className="px-1.5 py-0.5 bg-surface-elevated rounded text-sm font-mono" {...props}>
                {children}
              </code>
            );
          }
          return (
            <code className={`block p-3 bg-surface-sunken text-text-inverse rounded-lg text-sm font-mono overflow-x-auto ${className ?? ""}`} {...props}>
              {children}
            </code>
          );
        },
        a: ({ children, href }) => (
          <a href={href} className="text-accent-text hover:underline" target="_blank" rel="noopener noreferrer">
            {children}
          </a>
        ),
        p: ({ children }) => <p>{styleCitations(children, messageId)}</p>,
        li: ({ children }) => <li>{styleCitations(children, messageId)}</li>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

const CITATION_PATTERN = /\[(\d{1,2})\]/g;

function styleCitations(children: ReactNode, messageId?: string): ReactNode {
  if (!children) return children;

  if (typeof children === "string") {
    return replaceCitationsInText(children, messageId);
  }

  if (Array.isArray(children)) {
    return children.map((child, i) => {
      if (typeof child === "string") {
        return <span key={i}>{replaceCitationsInText(child, messageId)}</span>;
      }
      return child;
    });
  }

  return children;
}

function replaceCitationsInText(text: string, messageId?: string): ReactNode {
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  CITATION_PATTERN.lastIndex = 0;
  while ((match = CITATION_PATTERN.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const idx = match[1];
    const citationNum = parseInt(idx, 10);
    parts.push(
      <button
        key={`c${match.index}`}
        type="button"
        onClick={() => useChatStore.getState().highlightCitation(citationNum, messageId)}
        className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1 mx-0.5 rounded bg-accent-light text-accent-text text-[10px] font-semibold align-baseline cursor-pointer hover:bg-accent-muted transition-colors"
      >
        {idx}
      </button>,
    );
    lastIndex = match.index + match[0].length;
  }

  if (parts.length === 0) return text;
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
}
