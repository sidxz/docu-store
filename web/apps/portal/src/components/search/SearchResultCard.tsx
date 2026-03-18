import Link from "next/link";
import { useState, useEffect, type ReactNode } from "react";
import { Skeleton } from "primereact/skeleton";

import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { EntityTypeBadge } from "@/components/ui/EntityTypeBadge";
import { getAuthzClient } from "@/lib/authz-client";

interface SearchResultCardProps {
  title: string;
  href: string;
  score: number;
  preview?: string | null;
  entityType?: "artifact" | "page";
  secondaryLink?: { label: string; href: string };
  /** URL to a page thumbnail image (lazy-loaded with auth) */
  thumbnailSrc?: string;
  children?: ReactNode;
}

function AuthThumbnail({ src, href }: { src: string; href: string }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let revoke: string | null = null;
    const headers = getAuthzClient().getHeaders();

    fetch(src, { headers, signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(res.statusText);
        return res.blob();
      })
      .then((blob) => {
        if (controller.signal.aborted) return;
        revoke = URL.createObjectURL(blob);
        setBlobUrl(revoke);
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(true);
      });

    return () => {
      controller.abort();
      if (revoke) URL.revokeObjectURL(revoke);
    };
  }, [src]);

  if (error) return null;

  return (
    <Link href={href} className="relative hidden h-40 w-32 shrink-0 sm:block">
      {!blobUrl && (
        <Skeleton width="8rem" height="10rem" borderRadius="0.375rem" />
      )}
      {blobUrl && (
        <img
          src={blobUrl}
          alt=""
          className="h-40 w-32 rounded-md border border-border-subtle object-cover object-top"
        />
      )}
    </Link>
  );
}

export function SearchResultCard({
  title,
  href,
  score,
  preview,
  entityType,
  secondaryLink,
  thumbnailSrc,
  children,
}: SearchResultCardProps) {
  return (
    <div className="rounded-xl border border-border-default bg-surface-elevated p-4 transition-shadow hover:shadow-ds">
      <div className="flex items-start gap-4">
        {/* Thumbnail with auth */}
        {thumbnailSrc && (
          <AuthThumbnail src={thumbnailSrc} href={href} />
        )}

        {/* Content */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {entityType && <EntityTypeBadge type={entityType} />}
            <Link
              href={href}
              className="text-sm font-medium text-accent-text hover:underline"
            >
              {title}
            </Link>
          </div>
          {preview && (
            <p className="mt-1.5 text-sm leading-relaxed text-text-secondary line-clamp-3">
              {preview}
            </p>
          )}
          {secondaryLink && (
            <Link
              href={secondaryLink.href}
              className="mt-2 inline-block text-xs text-text-muted hover:text-text-secondary"
            >
              {secondaryLink.label}
            </Link>
          )}
          {children}
        </div>

        <ScoreBadge score={score} />
      </div>
    </div>
  );
}
