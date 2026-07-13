"use client";

import { useId } from "react";

/* DocuStore "cited compound" mark — a compound annotated out of the page,
   leader line back to the passage it came from: chemistry extracted from
   documents, answers that carry their citation.
   Canonical source of truth: docustore-site/src/components/layout/logo.tsx.
   Ink parts inherit currentColor — set a theme-aware text color on the
   consumer. The hexagon carries the brand gradient (self-contained hexes;
   the portal has no spectrum tokens). */
export function LogoMark({ className }: { className?: string }) {
  const id = useId();
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <defs>
        <linearGradient
          id={id}
          gradientUnits="userSpaceOnUse"
          x1="20"
          y1="16"
          x2="28"
          y2="7"
        >
          <stop offset="0" stopColor="#37d7fa" />
          <stop offset="0.4" stopColor="#4b72fe" />
          <stop offset="0.68" stopColor="#ff8df2" />
          <stop offset="1" stopColor="#ff8705" />
        </linearGradient>
      </defs>
      {/* page, right edge broken where the leader exits */}
      <path
        d="M19 12.9 V6 H5 V26 H19 V15.9"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      />
      <rect x="8" y="10" width="8" height="2" fill="currentColor" />
      <rect x="8" y="14" width="5" height="2" fill="currentColor" opacity=".33" />
      {/* the passage → the extracted compound */}
      <circle cx="10.5" cy="19.3" r="1.8" fill="currentColor" />
      <line
        x1="12.4"
        y1="18.2"
        x2="20.45"
        y2="13.55"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <polygon
        points="24,7.1 27.81,9.3 27.81,13.7 24,15.9 20.19,13.7 20.19,9.3"
        fill="none"
        stroke={`url(#${id})`}
        strokeWidth="2"
      />
    </svg>
  );
}
