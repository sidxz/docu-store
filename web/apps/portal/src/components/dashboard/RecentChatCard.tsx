"use client";

import Link from "next/link";
import { FileText, Library, ShieldCheck, MoreHorizontal } from "lucide-react";
import type { RecentConversation } from "@docu-store/types";
import { entityChipClass } from "@/lib/entity-colors";
import { SURFACES, conversationHref } from "@/lib/surfaces";
import { formatRelativeTime } from "@/lib/utils";
import { MoveToFolderMenu } from "@/components/folders/MoveToFolderMenu";
import { setChatDragData } from "@/components/folders/dnd";

export function RecentChatCard({ chat, workspace }: { chat: RecentConversation; workspace: string }) {
  const hasChips = chat.entities.length > 0;
  const hasDocs = !hasChips && chat.cited_documents.length > 0;
  // A conversation's surface is fixed at creation, so the card must route to
  // the surface it actually belongs to, not always /chat. Icon and colour come
  // from lib/surfaces so a recent card matches its sidebar entry exactly.
  const surface = chat.surface ?? "research";
  const isLiterature = surface === "literature";
  const SurfaceIcon = SURFACES[surface].icon;
  return (
    <div className="group relative">
    <Link
      href={conversationHref(workspace, surface, chat.conversation_id)}
      draggable
      onDragStart={(e) => setChatDragData(e, chat.conversation_id, chat.folder_id)}
      className="block rounded-xl border border-border-default bg-surface-elevated p-4 transition-all hover:border-primary/30 hover:shadow-ds-sm"
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-light">
          <SurfaceIcon className={`h-4 w-4 ${SURFACES[surface].iconColor}`} />
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
                  {isLiterature ? (
                    <Library className="h-3 w-3 shrink-0 text-text-muted" />
                  ) : (
                    <FileText className="h-3 w-3 shrink-0 text-text-muted" />
                  )}
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
      <div className="absolute right-2 top-2">
        <MoveToFolderMenu conversationId={chat.conversation_id} currentFolderId={chat.folder_id}>
          <button
            type="button"
            aria-label="Move to folder"
            className="rounded-md bg-surface-elevated/90 p-1 text-text-muted opacity-0 shadow-ds-sm backdrop-blur transition-opacity hover:bg-surface-sunken group-hover:opacity-100 data-[state=open]:bg-surface-sunken data-[state=open]:opacity-100"
          >
            <MoreHorizontal className="size-4" />
          </button>
        </MoveToFolderMenu>
      </div>
    </div>
  );
}
