"use client";

import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownRendererProps {
  content: string;
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  if (!content) return null;

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        table: ({ children }) => (
          <div className="overflow-x-auto my-3">
            <table className="w-full text-sm border-collapse border border-surface-200 dark:border-surface-700">
              {children}
            </table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-surface-100 dark:bg-surface-800">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-3 py-2 text-left font-semibold border border-surface-200 dark:border-surface-700">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-3 py-2 border border-surface-200 dark:border-surface-700">
            {children}
          </td>
        ),
        code: ({ className, children, ...props }) => {
          const isInline = !className;
          if (isInline) {
            return (
              <code className="px-1.5 py-0.5 bg-surface-100 dark:bg-surface-800 rounded text-sm font-mono" {...props}>
                {children}
              </code>
            );
          }
          return (
            <code className={`block p-3 bg-surface-900 dark:bg-surface-950 text-surface-100 rounded-lg text-sm font-mono overflow-x-auto ${className ?? ""}`} {...props}>
              {children}
            </code>
          );
        },
        a: ({ children, href }) => (
          <a href={href} className="text-primary-600 dark:text-primary-400 hover:underline" target="_blank" rel="noopener noreferrer">
            {children}
          </a>
        ),
        p: ({ children }) => <p>{styleCitations(children)}</p>,
        li: ({ children }) => <li>{styleCitations(children)}</li>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

const CITATION_PATTERN = /\[(\d{1,2})\]/g;

function styleCitations(children: ReactNode): ReactNode {
  if (!children) return children;

  if (typeof children === "string") {
    return replaceCitationsInText(children);
  }

  if (Array.isArray(children)) {
    return children.map((child, i) => {
      if (typeof child === "string") {
        return <span key={i}>{replaceCitationsInText(child)}</span>;
      }
      return child;
    });
  }

  return children;
}

function replaceCitationsInText(text: string): ReactNode {
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  CITATION_PATTERN.lastIndex = 0;
  while ((match = CITATION_PATTERN.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const idx = match[1];
    parts.push(
      <span
        key={`c${match.index}`}
        className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1 mx-0.5 rounded bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 text-[10px] font-semibold align-baseline"
      >
        {idx}
      </span>,
    );
    lastIndex = match.index + match[0].length;
  }

  if (parts.length === 0) return text;
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
}
