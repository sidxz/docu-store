"use client";

import Link from "next/link";
import type { ComponentProps } from "react";
import type { LucideIcon } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type LinkProps = ComponentProps<typeof Link>;

interface LinkButtonProps extends LinkProps {
  label: string;
  icon?: LucideIcon;
}

/**
 * Navigation button — renders as a single `<a>` with button styling.
 * Replaces the `<Link><Button></Link>` antipattern which nests
 * `<button>` inside `<a>` (broken semantics, double tab stops).
 */
export function LinkButton({ label, icon: Icon, className = "", ...linkProps }: LinkButtonProps) {
  return (
    <Link {...linkProps} className={cn(buttonVariants(), className)}>
      {Icon && <Icon className="size-4" />}
      <span>{label}</span>
    </Link>
  );
}
