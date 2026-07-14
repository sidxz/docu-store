"use client";

import { Fragment } from "react";
import Link from "next/link";
import { Coins, Globe, Lock, LogOut, Moon, Sun } from "lucide-react";
import { useAuthz } from "@sentinel-auth/react";
import type { MonthTokenUsage } from "@docu-store/types";

import { useSession } from "@/lib/auth";
import { useBreadcrumbs } from "@/hooks/use-breadcrumbs";
import { useUserTokenUsage } from "@/hooks/use-usage";
import { useThemeStore } from "@/lib/stores/theme-store";
import { useScopeStore } from "@/lib/stores/scope-store";
import { SearchCommand } from "./SearchCommand";
import { getInitials, formatTokens } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { FontSizeControl } from "./FontSizeControl";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";

export function Topbar() {
  const { user, workspace } = useSession();
  const { logout } = useAuthz();
  const breadcrumbs = useBreadcrumbs();
  const { theme, toggleTheme } = useThemeStore();
  const { defaultScope, setDefaultScope } = useScopeStore();
  const usage = useUserTokenUsage();

  const handleLogout = () => {
    logout();
    window.location.href = "/login";
  };

  // First crumb renders leftmost (workspace-level nav item); the rest follow
  // as navigable links, with the last one as the current (non-link) page.
  const firstCrumb = breadcrumbs[0];
  const restCrumbs = breadcrumbs.slice(1);

  const initials = getInitials(user.name);

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border-default bg-surface px-6 transition-colors duration-200">
      {/* Breadcrumbs */}
      {breadcrumbs.length > 1 ? (
        <Breadcrumb>
          <BreadcrumbList className="flex-nowrap">
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link
                  href={firstCrumb.href}
                  className="text-sm text-text-secondary transition-colors hover:text-text-primary"
                >
                  {firstCrumb.label}
                </Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            {restCrumbs.map((crumb, i) => (
              <Fragment key={crumb.href}>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  {i === restCrumbs.length - 1 ? (
                    <BreadcrumbPage className="text-sm font-medium text-text-primary">
                      {crumb.label}
                    </BreadcrumbPage>
                  ) : (
                    <BreadcrumbLink asChild>
                      <Link
                        href={crumb.href}
                        className="text-sm text-text-secondary transition-colors hover:text-text-primary"
                      >
                        {crumb.label}
                      </Link>
                    </BreadcrumbLink>
                  )}
                </BreadcrumbItem>
              </Fragment>
            ))}
          </BreadcrumbList>
        </Breadcrumb>
      ) : (
        <span className="text-sm font-medium text-text-primary">
          {firstCrumb?.label}
        </span>
      )}

      {/* Search command */}
      <SearchCommand />

      {/* Right section */}
      <div className="flex items-center gap-1">
        {/* User token usage total */}
        {usage.data && (usage.data.month.total > 0 || usage.data.month.limit !== null) && (
          <TokenBadge month={usage.data.month} />
        )}

        {/* Scope toggle */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              onClick={() => setDefaultScope(defaultScope === "workspace" ? "private" : "workspace")}
              aria-label={`Default visibility: ${defaultScope}. Click to switch.`}
            >
              {defaultScope === "workspace" ? (
                <Globe className="size-4" />
              ) : (
                <Lock className="size-4" />
              )}
              {defaultScope === "workspace" ? "Workspace" : "Private"}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">Default visibility for new documents</TooltipContent>
        </Tooltip>

        {/* Global text-size slider */}
        <FontSizeControl />

        {/* Theme toggle */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="rounded-full"
              onClick={toggleTheme}
              aria-label={theme === "light" ? "Dark mode" : "Light mode"}
            >
              {theme === "light" ? <Moon className="size-4" /> : <Sun className="size-4" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            {theme === "light" ? "Dark mode" : "Light mode"}
          </TooltipContent>
        </Tooltip>

        {/* Separator */}
        <Separator orientation="vertical" className="mx-1.5 data-[orientation=vertical]:h-5" />

        {/* User + logout */}
        <div className="flex items-center gap-2.5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-hover text-xs font-semibold text-white shadow-sm">
              {initials}
            </div>
            <div className="hidden sm:flex flex-col">
              <span className="text-sm font-medium leading-tight text-text-primary">
                {user.name || "User"}
              </span>
              <span className="text-xs leading-tight text-text-muted">
                {user.email || workspace.slug}
              </span>
            </div>
          </div>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="rounded-full"
                onClick={handleLogout}
                aria-label="Sign out"
              >
                <LogOut className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Sign out</TooltipContent>
          </Tooltip>
        </div>
      </div>
    </header>
  );
}

function TokenBadge({ month }: { month: MonthTokenUsage }) {
  const pct = month.limit ? month.total / month.limit : null;
  const color =
    pct !== null && pct >= 1
      ? "text-red-500"
      : pct !== null && pct >= 0.8
        ? "text-amber-500"
        : "text-text-muted";
  return (
    <span
      className={`hidden md:inline-flex items-center gap-1 px-2 text-xs font-mono tabular-nums ${color}`}
      title={`${month.total.toLocaleString()} tokens this month${
        month.limit !== null ? ` of ${month.limit.toLocaleString()} limit` : ""
      } — resets on the 1st (UTC)`}
    >
      <Coins className="size-3 text-amber-500" />
      {formatTokens(month.total)}
      {month.limit !== null && ` / ${formatTokens(month.limit)}`}
    </span>
  );
}
