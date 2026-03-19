"use client";

import Link from "next/link";
import { BreadCrumb } from "primereact/breadcrumb";
import { Button } from "primereact/button";
import { useAuthz } from "@sentinel-auth/react";

import { useSession } from "@/lib/auth";
import { useBreadcrumbs } from "@/hooks/use-breadcrumbs";
import { useThemeStore } from "@/lib/stores/theme-store";
import { useScopeStore } from "@/lib/stores/scope-store";
import { SearchCommand } from "./SearchCommand";

export function Topbar() {
  const { user, workspace } = useSession();
  const { logout } = useAuthz();
  const breadcrumbs = useBreadcrumbs();
  const { theme, toggleTheme } = useThemeStore();
  const { defaultScope, setDefaultScope } = useScopeStore();

  const handleLogout = () => {
    logout();
    window.location.href = "/login";
  };

  const bcModel = breadcrumbs.slice(0, -1).map((crumb) => ({
    label: crumb.label,
    template: () => (
      <Link
        href={crumb.href}
        className="text-sm text-text-secondary hover:text-text-primary transition-colors"
      >
        {crumb.label}
      </Link>
    ),
  }));

  const lastCrumb = breadcrumbs[breadcrumbs.length - 1];

  const initials = user.name
    ?.split(" ")
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase() || "?";

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border-default bg-surface px-6 transition-colors duration-200">
      {/* Breadcrumbs */}
      {breadcrumbs.length > 1 ? (
        <BreadCrumb
          model={bcModel}
          home={{
            label: lastCrumb?.label,
            template: () => (
              <span className="text-sm font-medium text-text-primary">
                {lastCrumb?.label}
              </span>
            ),
          }}
          className="border-none bg-transparent p-0"
        />
      ) : (
        <span className="text-sm font-medium text-text-primary">
          {lastCrumb?.label}
        </span>
      )}

      {/* Search command */}
      <SearchCommand />

      {/* Right section */}
      <div className="flex items-center gap-1">
        {/* Scope toggle */}
        <Button
          label={defaultScope === "workspace" ? "Workspace" : "Private"}
          icon={defaultScope === "workspace" ? "pi pi-globe" : "pi pi-lock"}
          onClick={() => setDefaultScope(defaultScope === "workspace" ? "private" : "workspace")}
          severity="secondary"
          text
          aria-label={`Default visibility: ${defaultScope}. Click to switch.`}
          tooltip="Default visibility for new documents"
          tooltipOptions={{ position: "bottom" }}
        />

        {/* Theme toggle */}
        <Button
          icon={theme === "light" ? "pi pi-moon" : "pi pi-sun"}
          onClick={toggleTheme}
          severity="secondary"
          text
          rounded
          aria-label={theme === "light" ? "Dark mode" : "Light mode"}
          tooltip={theme === "light" ? "Dark mode" : "Light mode"}
          tooltipOptions={{ position: "bottom" }}
        />

        {/* Separator */}
        <div className="mx-1.5 h-5 w-px bg-border-default" />

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
          <Button
            icon="pi pi-sign-out"
            onClick={handleLogout}
            severity="secondary"
            text
            rounded
            aria-label="Sign out"
            tooltip="Sign out"
            tooltipOptions={{ position: "bottom" }}
          />
        </div>
      </div>
    </header>
  );
}
