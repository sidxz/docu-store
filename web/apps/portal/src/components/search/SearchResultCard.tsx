"use client";

import Link from "next/link";
import { type ReactNode } from "react";

import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { EntityTypeBadge } from "@/components/ui/EntityTypeBadge";
import { AuthThumbnail } from "@/components/ui/TableThumbnail";
import { useAnalytics } from "@/hooks/use-analytics";

interface SearchResultCardProps {
  title: string;
  href: string;
  score: number;
  preview?: ReactNode;
  entityType?: "artifact" | "page";
  secondaryLink?: { label: string; href: string };
  /** URL to a page thumbnail image (lazy-loaded with auth) */
  thumbnailSrc?: string;
  children?: ReactNode;
  /** Result rank (0-based) for click tracking */
  rank?: number;
  /** Search type for click tracking */
  searchType?: string;
  /** Artifact ID for click tracking */
  artifactId?: string;
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
  rank,
  searchType,
  artifactId,
}: SearchResultCardProps) {
  const { trackEvent } = useAnalytics();

  const handleResultClick = () => {
    trackEvent("search_result_clicked", {
      ...(searchType ? { search_type: searchType } : {}),
      ...(rank != null ? { result_rank: rank } : {}),
      ...(artifactId ? { artifact_id: artifactId } : {}),
      score: Math.round(score * 1000) / 1000,
    });
  };

  return (
    <div className="rounded-xl border border-border-default bg-surface-elevated p-4 transition-shadow hover:shadow-ds-sm">
      <div className="flex items-start gap-4">
        {/* Thumbnail with auth */}
        {thumbnailSrc && (
          <AuthThumbnail src={thumbnailSrc} href={href} className="hidden sm:block" />
        )}

        {/* Content */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {entityType && <EntityTypeBadge type={entityType} />}
            <Link
              href={href}
              onClick={handleResultClick}
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
