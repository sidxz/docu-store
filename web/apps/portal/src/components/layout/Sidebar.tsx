"use client";

import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FileText,
  Search,
  Atom,
  MessageSquare,
  Activity,
  BarChart3,
  Settings,
  Sun,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  FlaskConical,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useAuthzHasRole } from "@sentinel-auth/react";

import { useThemeStore } from "@/lib/stores/theme-store";
import { useSidebarStore } from "@/lib/stores/sidebar-store";
import { useAnalytics } from "@/hooks/use-analytics";

import { SidebarNavItem } from "./SidebarNavItem";

interface NavItem {
  label: string;
  icon: LucideIcon;
  href: string;
  requireAdmin?: boolean;
}

const mainNav: NavItem[] = [
  { label: "Dashboard", icon: LayoutDashboard, href: "" },
  { label: "Documents", icon: FileText, href: "/documents" },
  { label: "Search", icon: Search, href: "/search" },
  { label: "Compounds", icon: Atom, href: "/compounds" },
  { label: "Chat", icon: MessageSquare, href: "/chat" },
  { label: "Stats", icon: BarChart3, href: "/stats", requireAdmin: true },
  { label: "Status", icon: Activity, href: "/status", requireAdmin: true },
];

export function Sidebar({ workspaceSlug }: { workspaceSlug: string }) {
  const pathname = usePathname();
  const { theme, toggleTheme } = useThemeStore();
  const { collapsed, toggleCollapsed } = useSidebarStore();
  const isAdmin = useAuthzHasRole("admin");
  const { trackEvent } = useAnalytics();

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
              DocuStore.io
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
          {mainNav.filter((item) => !item.requireAdmin || isAdmin).map((item) => (
            <div key={item.label} onClick={() => trackEvent("nav_clicked", { section: item.label.toLowerCase() })}>
              <SidebarNavItem
                icon={item.icon}
                label={item.label}
                href={`/${workspaceSlug}${item.href}`}
                isActive={isActive(item.href)}
                collapsed={collapsed}
              />
            </div>
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
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-text transition-all duration-200 hover:bg-sidebar-hover hover:text-white"
        >
          {theme === "light" ? (
            <Moon className="size-[1.125rem] shrink-0" />
          ) : (
            <Sun className="size-[1.125rem] shrink-0" />
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
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-text transition-all duration-200 hover:bg-sidebar-hover hover:text-white"
        >
          {collapsed ? (
            <PanelLeftOpen className="size-[1.125rem] shrink-0" />
          ) : (
            <PanelLeftClose className="size-[1.125rem] shrink-0" />
          )}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
