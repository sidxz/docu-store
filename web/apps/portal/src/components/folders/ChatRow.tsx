"use client";

import Link from "next/link";
import { MoreHorizontal } from "lucide-react";
import type { Conversation } from "@docu-store/types";
import { SURFACES, conversationHref } from "@/lib/surfaces";
import { formatRelativeTime } from "@/lib/utils";
import { MoveToFolderMenu } from "./MoveToFolderMenu";
import { setChatDragData } from "./dnd";

/** Compact chat row used in folder views (plain conversation, no enrichment). */
export function ChatRow({ chat, workspace }: { chat: Conversation; workspace: string }) {
  // A conversation's surface is fixed at creation, so the row must route to
  // the surface it actually belongs to, not always /chat. Folders hold both
  // surfaces at once, so the icon is how a dense row tells them apart.
  const surface = chat.surface ?? "research";
  const SurfaceIcon = SURFACES[surface].icon;
  return (
    <div className="group relative">
      <Link
        href={conversationHref(workspace, surface, chat.conversation_id)}
        draggable
        onDragStart={(e) => setChatDragData(e, chat.conversation_id, chat.folder_id)}
        className="block rounded-lg border border-border-default bg-surface-elevated px-4 py-3 pr-9 transition-all hover:border-primary/30 hover:shadow-ds-sm"
      >
        <div className="flex items-baseline justify-between gap-3">
          <p className="flex min-w-0 items-center gap-1.5 truncate text-sm font-medium text-text-primary">
            <SurfaceIcon className={`size-3.5 shrink-0 ${SURFACES[surface].iconColor}`} />
            <span className="truncate">{chat.title || "New Research"}</span>
          </p>
          <span className="shrink-0 text-xs text-text-muted">
            {formatRelativeTime(chat.updated_at)}
          </span>
        </div>
        <span className="text-xs text-text-muted">{chat.message_count} msgs</span>
      </Link>

      <div className="absolute right-2 top-2">
        <MoveToFolderMenu conversationId={chat.conversation_id} currentFolderId={chat.folder_id}>
          <button
            type="button"
            aria-label="Move to folder"
            className="rounded p-1 text-text-muted opacity-0 transition-opacity hover:bg-surface-sunken group-hover:opacity-100 data-[state=open]:bg-surface-sunken data-[state=open]:opacity-100"
          >
            <MoreHorizontal className="size-4" />
          </button>
        </MoveToFolderMenu>
      </div>
    </div>
  );
}
