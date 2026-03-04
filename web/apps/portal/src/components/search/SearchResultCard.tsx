import Link from "next/link";
import type { ReactNode } from "react";

import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { EntityTypeBadge } from "@/components/ui/EntityTypeBadge";

interface SearchResultCardProps {
  title: string;
  href: string;
  score: number;
  preview?: string | null;
  entityType?: "artifact" | "page";
  secondaryLink?: { label: string; href: string };
  children?: ReactNode;
}

export function SearchResultCard({
  title,
  href,
  score,
  preview,
  entityType,
  secondaryLink,
  children,
}: SearchResultCardProps) {
  return (
    <div className="rounded-xl border border-border-default bg-surface-elevated p-4 transition-shadow hover:shadow-ds">
      <div className="flex items-start justify-between gap-4">
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
