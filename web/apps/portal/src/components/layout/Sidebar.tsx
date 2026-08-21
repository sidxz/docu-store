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
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { useThemeStore } from "@/lib/stores/theme-store";
import { useSidebarStore } from "@/lib/stores/sidebar-store";
import { useAnalytics } from "@/hooks/use-analytics";

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
  { label: "Deep Research", icon: MessageSquare, href: "/chat", color: "text-indigo-500" },
  { label: "Search", icon: Search, href: "/search", color: "text-violet-500" },
  { label: "Documents", icon: FileText, href: "/documents", color: "text-amber-500" },
  { label: "Compounds", icon: Atom, href: "/compounds", color: "text-emerald-500" },
];

export function Sidebar({ workspaceSlug }: { workspaceSlug: string }) {
  const pathname = usePathname();
  const { theme, toggleTheme } = useThemeStore();
  const { collapsed, toggleCollapsed } = useSidebarStore();
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
          {mainNav.map((item) => (
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
