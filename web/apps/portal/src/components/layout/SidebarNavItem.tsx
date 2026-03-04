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
      className={`group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all duration-150 ${
        isActive
          ? "bg-sidebar-active text-sidebar-text-active font-medium"
          : "text-sidebar-text hover:bg-sidebar-hover hover:text-sidebar-text-active"
      }`}
    >
      {/* Active indicator bar */}
      {isActive && (
        <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r bg-accent" />
      )}

      <Icon className="h-[18px] w-[18px] shrink-0" />

      {!collapsed && (
        <>
          <span className="truncate">{label}</span>
          {badge !== undefined && (
            <span className="ml-auto rounded-full bg-white/10 px-1.5 py-0.5 text-xs leading-none">
              {badge}
            </span>
          )}
        </>
      )}
    </Link>
  );
}
