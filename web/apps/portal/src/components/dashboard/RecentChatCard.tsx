"use client";

import Link from "next/link";
import { MessageSquare, FileText, ShieldCheck } from "lucide-react";
import type { RecentConversation } from "@docu-store/types";
import { entityChipClass } from "@/lib/entity-colors";
import { formatRelativeTime } from "@/lib/utils";

export function RecentChatCard({ chat, workspace }: { chat: RecentConversation; workspace: string }) {
  const hasChips = chat.entities.length > 0;
  const hasDocs = !hasChips && chat.cited_documents.length > 0;
  return (
    <Link
      href={`/${workspace}/chat/${chat.conversation_id}`}
      className="group block rounded-xl border border-border-default bg-surface-elevated p-4 transition-all hover:border-primary/30 hover:shadow-ds-sm"
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-light">
          <MessageSquare className="h-4 w-4 text-accent-text" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-3">
            <p className="truncate text-sm font-medium text-text-primary">{chat.title || "New Chat"}</p>
            <span className="shrink-0 text-xs text-text-muted">{formatRelativeTime(chat.updated_at)}</span>
          </div>
          {chat.last_answer_snippet && (
            <p className={`mt-0.5 text-xs text-text-muted ${hasChips || hasDocs ? "line-clamp-1" : "line-clamp-2"}`}>
              {chat.last_answer_snippet}
            </p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {hasChips &&
              chat.entities.map((e) => (
                <span
                  key={`${e.type}-${e.text}`}
                  className={`inline-flex items-center rounded-md border bg-surface-elevated px-1.5 py-0.5 text-[11px] font-medium ${entityChipClass(e.type)}`}
                >
                  {e.text}
                </span>
              ))}
            {hasDocs &&
              chat.cited_documents.map((d) => (
                <span
                  key={d.artifact_id}
                  className="inline-flex max-w-[12rem] items-center gap-1 truncate rounded-md border border-border-default bg-surface-elevated px-1.5 py-0.5 text-[11px] text-text-secondary"
                >
                  <FileText className="h-3 w-3 shrink-0 text-text-muted" />
                  <span className="truncate">{d.title ?? "Document"}</span>
                </span>
              ))}
            <span className="ml-auto flex items-center gap-2 text-[11px] text-text-muted">
              <span>{chat.message_count} msgs</span>
              {chat.grounded === true && (
                <span className="flex items-center gap-0.5 text-ds-success">
                  <ShieldCheck className="h-3 w-3" />
                  {chat.grounded_confidence != null ? `${Math.round(chat.grounded_confidence * 100)}%` : "grounded"}
                </span>
              )}
            </span>
          </div>
        </div>
      </div>
    </Link>
  );
}
