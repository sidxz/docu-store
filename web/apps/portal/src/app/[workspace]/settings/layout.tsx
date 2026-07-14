"use client";

import { Settings } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useAuthzHasRole } from "@sentinel-auth/react";

import { PageHeader } from "@/components/ui/PageHeader";

interface SettingsTab {
  label: string;
  segment: string;
}

const TABS: SettingsTab[] = [
  { label: "General", segment: "general" },
  { label: "Chat", segment: "chat" },
  { label: "Workspace", segment: "workspace" },
];

const ADMIN_TABS: SettingsTab[] = [
  { label: "Token Settings", segment: "tokens" },
  { label: "Stats", segment: "stats" },
  { label: "Status", segment: "status" },
];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { workspace } = useParams<{ workspace: string }>();
  const isAdmin = useAuthzHasRole("admin");

  const base = `/${workspace}/settings`;

  const renderTab = ({ label, segment }: SettingsTab) => {
    const href = `${base}/${segment}`;
    const active = pathname.startsWith(href);
    return (
      <Link
        key={segment}
        href={href}
        className={`rounded-lg px-3 py-2 text-sm transition-colors ${
          active
            ? "bg-surface-sunken font-medium text-text-primary"
            : "text-text-muted hover:bg-surface-sunken/60 hover:text-text-primary"
        }`}
      >
        {label}
      </Link>
    );
  };

  return (
    <div>
      <PageHeader
        icon={Settings}
        title="Settings"
        subtitle="Workspace preferences and administration"
      />
      <div className="flex gap-8">
        <nav className="flex w-44 shrink-0 flex-col gap-0.5">
          {TABS.map(renderTab)}
          {isAdmin && ADMIN_TABS.length > 0 && (
            <>
              <div className="my-2 border-t border-border-default" />
              {ADMIN_TABS.map(renderTab)}
            </>
          )}
        </nav>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
