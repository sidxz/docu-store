"use client";

import { useRef } from "react";
import { useDropzone, type Accept } from "react-dropzone";
import { UploadCloud, FolderOpen, FilePlus2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const ACCEPT: Accept = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
  "application/vnd.ms-powerpoint": [".ppt"],
  "application/msword": [".doc"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
};
const MAX_FILE_SIZE = 100_000_000;

export function UploadDropzone({ onFiles, onReject, disabled }: { onFiles: (files: File[]) => void; onReject?: (count: number) => void; disabled?: boolean }) {
  const folderRef = useRef<HTMLInputElement>(null);
  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop: (accepted) => accepted.length && onFiles(accepted),
    onDropRejected: (rejections) => onReject?.(rejections.length),
    accept: ACCEPT,
    maxSize: MAX_FILE_SIZE,
    multiple: true,
    noClick: true,
    disabled,
  });

  return (
    <div
      {...getRootProps()}
      className={cn(
        "flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 text-center transition-colors",
        isDragActive ? "border-primary bg-accent-light" : "border-border-default",
      )}
    >
      <input {...getInputProps()} />
      {/* webkitdirectory input for folder selection — filtered by the same accept in the parent's onFiles */}
      <input
        ref={folderRef}
        type="file"
        // @ts-expect-error non-standard attributes for folder selection
        webkitdirectory=""
        directory=""
        multiple
        hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          if (files.length) onFiles(files);
          e.target.value = "";
        }}
      />
      <div className="mb-3 flex size-12 items-center justify-center rounded-xl bg-accent-light">
        <UploadCloud className="size-6 text-accent-text" />
      </div>
      <p className="text-sm font-medium text-text-primary">Drag files or a folder here</p>
      <p className="mt-1 text-xs text-text-muted">PDF, PPT, PPTX, DOC, DOCX · up to 100 MB each</p>
      <div className="mt-4 flex gap-2">
        <Button type="button" variant="outline" size="sm" onClick={open} disabled={disabled}>
          <FilePlus2 className="size-4" />Browse files
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={() => folderRef.current?.click()} disabled={disabled}>
          <FolderOpen className="size-4" />Select folder
        </Button>
      </div>
    </div>
  );
}
