"use client";

import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FileText,
  Search,
  Atom,
  MessageSquare,
  Settings,
  Sun,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  FlaskConical,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { useThemeStore } from "@/lib/stores/theme-store";
import { useSidebarStore } from "@/lib/stores/sidebar-store";

import { SidebarNavItem } from "./SidebarNavItem";

interface NavItem {
  label: string;
  icon: LucideIcon;
  href: string;
}

const mainNav: NavItem[] = [
  { label: "Dashboard", icon: LayoutDashboard, href: "" },
  { label: "Documents", icon: FileText, href: "/documents" },
  { label: "Search", icon: Search, href: "/search" },
  { label: "Compounds", icon: Atom, href: "/compounds" },
  { label: "Chat", icon: MessageSquare, href: "/chat" },
];

export function Sidebar({ workspaceSlug }: { workspaceSlug: string }) {
  const pathname = usePathname();
  const { theme, toggleTheme } = useThemeStore();
  const { collapsed, toggleCollapsed } = useSidebarStore();

  const isActive = (href: string) => {
    const fullHref = `/${workspaceSlug}${href}`;
    return href === ""
      ? pathname === `/${workspaceSlug}`
      : pathname.startsWith(fullHref);
  };

  return (
    <aside
      className={`flex h-full flex-col bg-sidebar transition-[width] duration-200 ${
        collapsed ? "w-16" : "w-56"
      }`}
    >
      {/* Brand */}
      <div className="flex h-14 items-center gap-3 border-b border-sidebar-border px-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-blue-400 shadow-sm">
          <FlaskConical className="h-4 w-4 text-white" />
        </div>
        {!collapsed && (
          <div className="flex flex-col">
            <span className="text-sm font-bold tracking-wide text-white">
              DOCU.STORE
            </span>
            <span className="text-xs uppercase tracking-widest text-sidebar-text opacity-60">
              {workspaceSlug}
            </span>
          </div>
        )}
      </div>

      {/* Main navigation */}
      <nav className="flex flex-1 flex-col px-2 py-4">
        {!collapsed && (
          <span className="mb-2 px-3 text-xs font-semibold uppercase tracking-widest text-sidebar-text opacity-40">
            Navigation
          </span>
        )}
        <div className="flex flex-col gap-0.5">
          {mainNav.map((item) => (
            <SidebarNavItem
              key={item.label}
              icon={item.icon}
              label={item.label}
              href={`/${workspaceSlug}${item.href}`}
              isActive={isActive(item.href)}
              collapsed={collapsed}
            />
          ))}
        </div>
      </nav>

      {/* Bottom section */}
      <div className="border-t border-sidebar-border px-2 py-3 space-y-0.5">
        <SidebarNavItem
          icon={Settings}
          label="Settings"
          href={`/${workspaceSlug}/settings`}
          isActive={pathname.startsWith(`/${workspaceSlug}/settings`)}
          collapsed={collapsed}
        />

        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          title={collapsed ? (theme === "light" ? "Dark mode" : "Light mode") : undefined}
          aria-label={theme === "light" ? "Dark mode" : "Light mode"}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-text transition-all duration-200 hover:bg-white/[0.04] hover:text-white"
        >
          {theme === "light" ? (
            <Moon className="h-[18px] w-[18px] shrink-0" />
          ) : (
            <Sun className="h-[18px] w-[18px] shrink-0" />
          )}
          {!collapsed && (
            <span>{theme === "light" ? "Dark mode" : "Light mode"}</span>
          )}
        </button>

        {/* Collapse toggle */}
        <button
          onClick={toggleCollapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-text transition-all duration-200 hover:bg-white/[0.04] hover:text-white"
        >
          {collapsed ? (
            <PanelLeftOpen className="h-[18px] w-[18px] shrink-0" />
          ) : (
            <PanelLeftClose className="h-[18px] w-[18px] shrink-0" />
          )}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
