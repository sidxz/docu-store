import Link from "next/link";
import { useState, type ReactNode } from "react";

import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { EntityTypeBadge } from "@/components/ui/EntityTypeBadge";

interface SearchResultCardProps {
  title: string;
  href: string;
  score: number;
  preview?: string | null;
  entityType?: "artifact" | "page";
  secondaryLink?: { label: string; href: string };
  /** URL to a page thumbnail image (lazy-loaded) */
  thumbnailSrc?: string;
  children?: ReactNode;
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
  const [thumbLoaded, setThumbLoaded] = useState(false);
  const [thumbError, setThumbError] = useState(false);

  return (
    <div className="rounded-xl border border-border-default bg-surface-elevated p-4 transition-shadow hover:shadow-ds">
      <div className="flex items-start gap-4">
        {/* Thumbnail */}
        {thumbnailSrc && !thumbError && (
          <Link
            href={href}
            className="relative hidden h-40 w-32 shrink-0 sm:block"
          >
            {!thumbLoaded && (
              <div className="absolute inset-0 animate-pulse rounded-md bg-border-subtle" />
            )}
            <img
              src={thumbnailSrc}
              alt=""
              loading="lazy"
              className={`h-40 w-32 rounded-md border border-border-subtle object-cover object-top transition-opacity ${thumbLoaded ? "opacity-100" : "opacity-0"}`}
              onLoad={() => setThumbLoaded(true)}
              onError={() => setThumbError(true)}
            />
          </Link>
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
