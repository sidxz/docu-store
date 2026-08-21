"use client";

import { useState } from "react";
import { Folder, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import type { ChatFolder } from "@docu-store/types";
import { formatRelativeTime } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useConfirm } from "@/components/providers/ConfirmProvider";
import { useDeleteFolder, useSetChatFolder } from "@/hooks/use-folders";
import { FolderNameDialog } from "./FolderNameDialog";
import { CHAT_FROM, CHAT_ID } from "./dnd";

export function FolderTile({
  folder,
  active,
  onOpen,
}: {
  folder: ChatFolder;
  active?: boolean;
  onOpen: () => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const setChatFolder = useSetChatFolder();
  const deleteFolder = useDeleteFolder();
  const confirm = useConfirm();

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const id = e.dataTransfer.getData(CHAT_ID);
    const from = e.dataTransfer.getData(CHAT_FROM) || null;
    if (id && from !== folder.folder_id) {
      setChatFolder.mutate({
        conversationId: id,
        toFolderId: folder.folder_id,
        fromFolderId: from,
      });
    }
  };

  const handleDelete = async () => {
    if (
      await confirm({
        title: `Delete "${folder.name}"?`,
        description: "The folder is removed, but its research sessions stay — they're just unfiled.",
        confirmLabel: "Delete",
        destructive: true,
      })
    ) {
      deleteFolder.mutate(folder.folder_id);
    }
  };

  return (
    <div className="group/tile relative">
      <button
        type="button"
        onClick={onOpen}
        onDragOver={(e) => {
          if (e.dataTransfer.types.includes(CHAT_ID)) {
            e.preventDefault();
            setDragOver(true);
          }
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`flex items-center gap-2 rounded-lg border px-3 py-2 pr-8 text-left transition-all ${
          dragOver
            ? "border-primary bg-accent-light ring-2 ring-primary/40"
            : active
              ? "border-primary/40 bg-accent-light"
              : "border-border-default bg-surface-elevated hover:border-primary/30 hover:shadow-ds-sm"
        }`}
      >
        <Folder className="size-4 shrink-0 text-feature-folder" />
        <span className="flex min-w-0 flex-col">
          <span className="truncate text-sm font-medium text-text-primary">
            {folder.name}
          </span>
          <span className="truncate text-[11px] text-text-muted">
            {folder.chat_count} {folder.chat_count === 1 ? "session" : "sessions"} · Updated{" "}
            {formatRelativeTime(folder.updated_at)}
          </span>
        </span>
      </button>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            aria-label={`${folder.name} options`}
            className="absolute right-1.5 top-1.5 rounded p-1 text-text-muted opacity-0 transition-opacity hover:bg-surface-sunken group-hover/tile:opacity-100 data-[state=open]:opacity-100"
          >
            <MoreHorizontal className="size-4" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => setRenameOpen(true)}>
            <Pencil className="size-4" />
            Rename
          </DropdownMenuItem>
          <DropdownMenuItem variant="destructive" onSelect={() => handleDelete()}>
            <Trash2 className="size-4" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <FolderNameDialog
        open={renameOpen}
        onOpenChange={setRenameOpen}
        mode="rename"
        folderId={folder.folder_id}
        initialName={folder.name}
      />
    </div>
  );
}
