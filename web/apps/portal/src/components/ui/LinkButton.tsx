"use client";

import Link from "next/link";
import type { ComponentProps } from "react";

type LinkProps = ComponentProps<typeof Link>;

interface LinkButtonProps extends LinkProps {
  label: string;
  icon?: string;
}

/**
 * Navigation button — renders as a single `<a>` with button styling.
 * Replaces the `<Link><Button></Link>` antipattern which nests
 * `<button>` inside `<a>` (broken semantics, double tab stops).
 */
export function LinkButton({ label, icon, className = "", ...linkProps }: LinkButtonProps) {
  return (
    <Link
      {...linkProps}
      className={`p-button p-component inline-flex items-center justify-center no-underline ${className}`}
    >
      {icon && <span className={`p-button-icon p-button-icon-left ${icon}`} />}
      <span className="p-button-label">{label}</span>
    </Link>
  );
}
