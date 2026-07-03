"use client";

import { useState, type ReactNode } from "react";
import { FolderPlus } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useFolders, useSetChatFolder } from "@/hooks/use-folders";
import { FolderNameDialog } from "./FolderNameDialog";

interface MoveToFolderMenuProps {
  conversationId: string;
  currentFolderId: string | null;
  /** The trigger element. */
  children: ReactNode;
  align?: "start" | "end";
}

export function MoveToFolderMenu({
  conversationId,
  currentFolderId,
  children,
  align = "end",
}: MoveToFolderMenuProps) {
  const { data: folders } = useFolders();
  const setChatFolder = useSetChatFolder();
  const [createOpen, setCreateOpen] = useState(false);

  const move = (toFolderId: string | null) => {
    if (toFolderId === currentFolderId) return;
    setChatFolder.mutate({ conversationId, toFolderId, fromFolderId: currentFolderId });
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>{children}</DropdownMenuTrigger>
        <DropdownMenuContent align={align} className="min-w-52">
          <DropdownMenuLabel>Move to folder</DropdownMenuLabel>
          {folders && folders.length > 0 && (
            <DropdownMenuRadioGroup
              value={currentFolderId ?? ""}
              onValueChange={(v) => move(v)}
            >
              {folders.map((f) => (
                <DropdownMenuRadioItem key={f.folder_id} value={f.folder_id}>
                  <span className="truncate">{f.name}</span>
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          )}
          {currentFolderId && (
            <DropdownMenuItem onSelect={() => move(null)}>
              Remove from folder
            </DropdownMenuItem>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setCreateOpen(true)}>
            <FolderPlus className="size-4" />
            New folder…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <FolderNameDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        mode="create"
        onCreated={(folder) =>
          setChatFolder.mutate({
            conversationId,
            toFolderId: folder.folder_id,
            fromFolderId: currentFolderId,
          })
        }
      />
    </>
  );
}
