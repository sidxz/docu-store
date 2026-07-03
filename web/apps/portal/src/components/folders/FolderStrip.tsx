"use client";

import { useState } from "react";
import { FolderPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useFolders } from "@/hooks/use-folders";
import { FolderTile } from "./FolderTile";
import { FolderNameDialog } from "./FolderNameDialog";

interface FolderStripProps {
  selectedFolderId: string | null;
  onSelect: (id: string | null) => void;
}

/** Row of folder tiles (drop targets) plus a "New Folder" button. */
export function FolderStrip({ selectedFolderId, onSelect }: FolderStripProps) {
  const { data: folders } = useFolders();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="mb-4 flex flex-wrap items-stretch gap-2">
      {folders?.map((f) => (
        <FolderTile
          key={f.folder_id}
          folder={f}
          active={selectedFolderId === f.folder_id}
          onOpen={() => onSelect(selectedFolderId === f.folder_id ? null : f.folder_id)}
        />
      ))}
      <Button
        size="sm"
        className="self-center"
        onClick={() => setCreateOpen(true)}
      >
        <FolderPlus className="size-4" />
        New Folder
      </Button>
      <FolderNameDialog open={createOpen} onOpenChange={setCreateOpen} mode="create" />
    </div>
  );
}
