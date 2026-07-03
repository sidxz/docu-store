"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import type { ChatFolder } from "@docu-store/types";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useCreateFolder, useRenameFolder } from "@/hooks/use-folders";

interface FolderNameDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode?: "create" | "rename";
  folderId?: string;
  initialName?: string;
  /** Called with the created folder (create mode only). */
  onCreated?: (folder: ChatFolder) => void;
}

export function FolderNameDialog({
  open,
  onOpenChange,
  mode = "create",
  folderId,
  initialName = "",
  onCreated,
}: FolderNameDialogProps) {
  const [name, setName] = useState(initialName);
  const createFolder = useCreateFolder();
  const renameFolder = useRenameFolder();
  const pending = createFolder.isPending || renameFolder.isPending;

  useEffect(() => {
    if (open) setName(initialName);
  }, [open, initialName]);

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed || pending) return;
    try {
      if (mode === "rename" && folderId) {
        await renameFolder.mutateAsync({ folderId, name: trimmed });
      } else {
        const folder = await createFolder.mutateAsync(trimmed);
        onCreated?.(folder);
      }
    } catch (err) {
      // Keep the dialog open so the user can fix the name and retry.
      toast.error(mode === "rename" ? "Couldn't rename folder" : "Couldn't create folder", {
        description: err instanceof Error ? err.message : undefined,
      });
      return;
    }
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{mode === "rename" ? "Rename folder" : "New folder"}</DialogTitle>
        </DialogHeader>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Folder name"
          autoFocus
          maxLength={100}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submit();
            }
          }}
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!name.trim() || pending}>
            {mode === "rename" ? "Rename" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
