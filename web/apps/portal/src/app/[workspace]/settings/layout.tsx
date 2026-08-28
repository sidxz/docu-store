"use client";

import { Settings } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useAuthzHasRole } from "@duar-auth/react";

import { PageHeader } from "@/components/ui/PageHeader";
import { useLlmProvider } from "@/hooks/use-llm-provider";
import { useAppConfig } from "@/lib/app-config";

interface SettingsTab {
  label: string;
  segment: string;
}

const TABS: SettingsTab[] = [
  { label: "General", segment: "general" },
  { label: "Deep Research", segment: "chat" },
  { label: "Usage", segment: "usage" },
  { label: "Workspace", segment: "workspace" },
];

const ADMIN_TABS: SettingsTab[] = [
  { label: "Token Settings", segment: "tokens" },
  { label: "Stats", segment: "stats" },
  { label: "Status", segment: "status" },
];

/** Public edition only — what the user agreed to at sign-up, kept reachable. */
const LEGAL_LINKS = [
  { label: "Terms of Use", href: "https://docustore.io/terms" },
  { label: "Privacy Policy", href: "https://docustore.io/privacy" },
];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { workspace } = useParams<{ workspace: string }>();
  const isAdmin = useAuthzHasRole("admin");
  // Training export is gated server side on `artifacts:hiledit`, held by editor and above.
  const canExportTraining = useAuthzHasRole("editor");
  const provider = useLlmProvider();
  const { selfServeEnabled } = useAppConfig();
  const tabs = [
    ...TABS,
    ...(canExportTraining ? [{ label: "Training Export", segment: "training-export" }] : []),
    ...(provider.data?.enabled ? [{ label: "AI Provider", segment: "llm" }] : []),
  ];

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
          {tabs.map(renderTab)}
          {isAdmin && ADMIN_TABS.length > 0 && (
            <>
              <div className="my-2 border-t border-border-default" />
              {ADMIN_TABS.map(renderTab)}
            </>
          )}
          {selfServeEnabled && (
            <>
              <div className="my-2 border-t border-border-default" />
              {LEGAL_LINKS.map(({ label, href }) => (
                <a
                  key={href}
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-md px-3 py-2 text-sm text-text-muted transition-colors hover:bg-surface-hover hover:text-text-default"
                >
                  {label}
                </a>
              ))}
            </>
          )}
        </nav>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
