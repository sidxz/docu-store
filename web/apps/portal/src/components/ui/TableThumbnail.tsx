"use client";

import Link from "next/link";
import { type ReactNode } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuthBlobUrl } from "@/hooks/use-auth-blob-url";
import { API_URL } from "@/lib/constants";

const sizes = {
  xs: { cls: "w-16 h-20", radius: "rounded-md" },
  sm: { cls: "h-12 w-12", radius: "rounded-sm" },
  md: { cls: "h-20 w-20", radius: "rounded-md" },
  lg: { cls: "h-32 w-32", radius: "rounded-md" },
} as const;

interface AuthThumbnailProps {
  /** Direct image URL (fetched with auth headers). Takes priority over artifactId. */
  src?: string;
  /** Shorthand: constructs src from artifact page 0 thumbnail. */
  artifactId?: string;
  href: string;
  size?: keyof typeof sizes;
  className?: string;
  /** Rendered when the image fails to load. Defaults to null. */
  errorFallback?: ReactNode;
}

export function AuthThumbnail({
  src,
  artifactId,
  href,
  size = "lg",
  className,
  errorFallback = null,
}: AuthThumbnailProps) {
  const resolvedSrc = src ?? `${API_URL}/artifacts/${artifactId}/pages/0/image?size=thumb`;
  const { blobUrl, error } = useAuthBlobUrl(resolvedSrc);
  const s = sizes[size];

  if (error) return errorFallback;

  return (
    <Link href={href} className={`block shrink-0 ${s.cls} ${className ?? ""}`}>
      {!blobUrl && <Skeleton className={`${s.cls} ${s.radius}`} />}
      {blobUrl && (
        <img
          src={blobUrl}
          alt=""
          className={`${s.cls} rounded-md border border-border-subtle object-cover object-top`}
        />
      )}
    </Link>
  );
}

/** @deprecated Use AuthThumbnail instead */
export const TableThumbnail = AuthThumbnail;
