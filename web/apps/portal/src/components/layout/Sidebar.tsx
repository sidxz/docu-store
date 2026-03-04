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

  // Dashboard (href="") matches only the exact workspace root;
  // all other items use startsWith so child routes stay highlighted.
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
      <div className="flex h-14 items-center gap-2.5 border-b border-sidebar-border px-4">
        <FlaskConical className="h-5 w-5 shrink-0 text-accent" />
        {!collapsed && (
          <div className="flex flex-col">
            <span className="text-sm font-bold tracking-wide text-white">
              DAIKON
            </span>
            <span className="text-[10px] uppercase tracking-widest text-sidebar-text">
              {workspaceSlug}
            </span>
          </div>
        )}
      </div>

      {/* Main navigation */}
      <nav className="flex flex-1 flex-col gap-0.5 px-2 py-3">
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
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-text transition-colors duration-150 hover:bg-sidebar-hover hover:text-sidebar-text-active"
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
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-text transition-colors duration-150 hover:bg-sidebar-hover hover:text-sidebar-text-active"
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
