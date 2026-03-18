"use client";

import Link from "next/link";
import type { LucideIcon } from "lucide-react";

interface SidebarNavItemProps {
  icon: LucideIcon;
  label: string;
  href: string;
  isActive: boolean;
  collapsed: boolean;
  badge?: string | number;
}

export function SidebarNavItem({
  icon: Icon,
  label,
  href,
  isActive,
  collapsed,
  badge,
}: SidebarNavItemProps) {
  return (
    <Link
      href={href}
      title={collapsed ? label : undefined}
      aria-current={isActive ? "page" : undefined}
      className={`group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all duration-200 ${
        isActive
          ? "bg-white/[0.08] text-white font-medium shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]"
          : "text-sidebar-text hover:bg-white/[0.04] hover:text-white"
      }`}
    >
      {/* Active indicator bar */}
      {isActive && (
        <span className="absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r-full bg-accent shadow-[0_0_6px_rgba(59,130,246,0.5)]" />
      )}

      <Icon className={`h-[18px] w-[18px] shrink-0 transition-colors ${isActive ? "text-accent" : ""}`} />

      {!collapsed && (
        <>
          <span className="truncate">{label}</span>
          {badge !== undefined && (
            <span className="ml-auto rounded-full bg-white/10 px-1.5 py-0.5 text-xs font-medium leading-none">
              {badge}
            </span>
          )}
        </>
      )}
    </Link>
  );
}
