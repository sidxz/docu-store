"use client";

import { useAuthBlobUrl } from "@/hooks/use-auth-blob-url";
import { Skeleton } from "@/components/ui/skeleton";
import { API_URL } from "@/lib/constants";

interface PdfEmbedProps {
  artifactId: string;
  /** If provided, scrolls the embedded PDF to this page number (1-based). */
  pageNumber?: number;
}

export function PdfEmbed({ artifactId, pageNumber }: PdfEmbedProps) {
  const { blobUrl, error } = useAuthBlobUrl(
    `${API_URL}/artifacts/${artifactId}/pdf`,
  );

  if (error) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg border border-ds-error/20 bg-ds-error/5">
        <p className="text-sm text-ds-error">Failed to load PDF</p>
      </div>
    );
  }

  const src = blobUrl
    ? pageNumber
      ? `${blobUrl}#page=${pageNumber}`
      : blobUrl
    : undefined;

  return (
    <div className="overflow-hidden rounded-lg border border-border-default">
      {!blobUrl && (
        <Skeleton className="h-[80vh] w-full rounded-none bg-surface-elevated" />
      )}
      {src && (
        <iframe
          src={src}
          className="h-[80vh] w-full"
          title={pageNumber ? `PDF page ${pageNumber}` : "PDF Viewer"}
        />
      )}
    </div>
  );
}
