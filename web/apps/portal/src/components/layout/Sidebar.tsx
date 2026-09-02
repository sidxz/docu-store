"use client";

import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FileText,
  Search,
  Atom,
  MessageSquare,
  Library,
  Settings,
  Code2,
  Sun,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { SURFACE_ICON, SURFACE_ICON_COLOR } from "@/lib/surfaces";
import { useThemeStore } from "@/lib/stores/theme-store";
import { useSidebarStore } from "@/lib/stores/sidebar-store";
import { useAnalytics } from "@/hooks/use-analytics";
import { useAppConfig } from "@/lib/app-config";

import { SidebarNavItem } from "./SidebarNavItem";
import { LogoMark } from "@/components/ui/LogoMark";

interface NavItem {
  label: string;
  icon: LucideIcon;
  href: string;
  color: string;
}

const mainNav: NavItem[] = [
  { label: "Dashboard", icon: LayoutDashboard, href: "", color: "text-blue-500" },
  { label: "Deep Research", icon: SURFACE_ICON.research, href: "/chat", color: SURFACE_ICON_COLOR.research },
  { label: "Search", icon: Search, href: "/search", color: "text-violet-500" },
  { label: "Documents", icon: FileText, href: "/documents", color: "text-amber-500" },
  { label: "Compounds", icon: Atom, href: "/compounds", color: "text-emerald-500" },
];

/** Sits after Deep Research: same shape of surface, a different corpus.
 *  Icon and colour come from lib/surfaces so the conversation rows, empty
 *  states and dashboard cards cannot drift away from what the nav shows. */
const literatureNav: NavItem = {
  label: "Literature",
  icon: SURFACE_ICON.literature,
  href: "/literature",
  color: SURFACE_ICON_COLOR.literature,
};

export function Sidebar({ workspaceSlug }: { workspaceSlug: string }) {
  const pathname = usePathname();
  const { theme, toggleTheme } = useThemeStore();
  const { collapsed, toggleCollapsed } = useSidebarStore();
  const { trackEvent } = useAnalytics();
  const { literatureEnabled } = useAppConfig();

  const nav = literatureEnabled
    ? [...mainNav.slice(0, 2), literatureNav, ...mainNav.slice(2)]
    : mainNav;

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
        <LogoMark className="h-8 w-8 shrink-0 text-sidebar-text-active" />
        {!collapsed && (
          <div className="flex flex-col">
            <span
              className="text-[15px] font-medium tracking-tight text-sidebar-text-active"
              style={{ fontFamily: "var(--font-overused-grotesk), ui-sans-serif, sans-serif" }}
            >
              DocuStore<span className="opacity-40">.io</span>
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
          {nav.map((item) => (
            <div key={item.label} onClick={() => trackEvent("nav_clicked", { section: item.label.toLowerCase() })}>
              <SidebarNavItem
                icon={item.icon}
                label={item.label}
                href={`/${workspaceSlug}${item.href}`}
                isActive={isActive(item.href)}
                collapsed={collapsed}
                iconColor={item.color}
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
          iconColor="text-slate-500"
        />

        {/* Source code — required by AGPL-3.0 §13 for network-interactive use */}
        <a
          href="https://github.com/sidxz/docu-store"
          target="_blank"
          rel="noopener noreferrer"
          title={collapsed ? "Source code (AGPL-3.0)" : undefined}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-text transition-all duration-200 hover:bg-sidebar-hover hover:text-sidebar-text-active"
        >
          <Code2 className="size-[1.125rem] shrink-0" />
          {!collapsed && <span>Source code</span>}
        </a>

        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          title={collapsed ? (theme === "light" ? "Dark mode" : "Light mode") : undefined}
          aria-label={theme === "light" ? "Dark mode" : "Light mode"}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-text transition-all duration-200 hover:bg-sidebar-hover hover:text-sidebar-text-active"
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
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-text transition-all duration-200 hover:bg-sidebar-hover hover:text-sidebar-text-active"
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
