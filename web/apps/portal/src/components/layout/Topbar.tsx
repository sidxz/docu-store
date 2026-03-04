"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight, Search, Sun, Moon } from "lucide-react";

import { useSession } from "@/lib/auth";
import { useBreadcrumbs } from "@/hooks/use-breadcrumbs";
import { useThemeStore } from "@/lib/stores/theme-store";

export function Topbar() {
  const { user, workspace } = useSession();
  const breadcrumbs = useBreadcrumbs();
  const { theme, toggleTheme } = useThemeStore();
  const router = useRouter();

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border-default bg-surface px-6 transition-colors duration-200">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-1 text-sm">
        {breadcrumbs.map((crumb, i) => (
          <span key={crumb.href} className="flex items-center gap-1">
            {i > 0 && (
              <ChevronRight className="h-3.5 w-3.5 text-text-muted" />
            )}
            {i < breadcrumbs.length - 1 ? (
              <Link
                href={crumb.href}
                className="text-text-secondary hover:text-text-primary transition-colors"
              >
                {crumb.label}
              </Link>
            ) : (
              <span className="font-medium text-text-primary">
                {crumb.label}
              </span>
            )}
          </span>
        ))}
      </nav>

      {/* Search pill */}
      <button
        onClick={() => router.push(`/${workspace.slug}/search`)}
        className="flex items-center gap-2 rounded-lg border border-border-default bg-surface-sunken px-3 py-1.5 text-sm text-text-muted transition-colors hover:border-accent hover:text-text-secondary"
      >
        <Search className="h-3.5 w-3.5" />
        <span>Search...</span>
        <kbd className="ml-2 rounded border border-border-default bg-surface px-1.5 py-0.5 text-[10px] font-medium text-text-muted">
          {"\u2318"}K
        </kbd>
      </button>

      {/* Right section */}
      <div className="flex items-center gap-3">
        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-accent-light hover:text-accent-text"
          title={theme === "light" ? "Dark mode" : "Light mode"}
        >
          {theme === "light" ? (
            <Moon className="h-4 w-4" />
          ) : (
            <Sun className="h-4 w-4" />
          )}
        </button>

        {/* User avatar */}
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent/10 text-sm font-medium text-accent-text">
            {user.name.charAt(0)}
          </div>
        </div>
      </div>
    </header>
  );
}
