"use client";

import { Settings, Sun, Moon, Monitor } from "lucide-react";

import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardHeader } from "@/components/ui/Card";
import { useThemeStore } from "@/lib/stores/theme-store";
import { useSession } from "@/lib/auth";

export default function SettingsPage() {
  const { theme, setTheme } = useThemeStore();
  const { workspace } = useSession();

  return (
    <div>
      <PageHeader
        icon={Settings}
        title="Settings"
        subtitle="Manage workspace preferences"
      />

      <div className="max-w-2xl space-y-6">
        {/* Theme */}
        <Card>
          <CardHeader title="Appearance" />
          <div className="flex gap-3">
            {[
              { value: "light" as const, icon: Sun, label: "Light" },
              { value: "dark" as const, icon: Moon, label: "Dark" },
            ].map(({ value, icon: Icon, label }) => (
              <button
                key={value}
                onClick={() => setTheme(value)}
                className={`flex items-center gap-2 rounded-lg border px-4 py-3 text-sm font-medium transition-colors ${
                  theme === value
                    ? "border-accent bg-accent-light text-accent-text"
                    : "border-border-default text-text-secondary hover:border-accent/50"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            ))}
          </div>
        </Card>

        {/* Workspace info */}
        <Card>
          <CardHeader title="Workspace" />
          <div className="space-y-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-text-muted">Name</span>
              <span className="text-text-primary">{workspace.name}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-text-muted">Slug</span>
              <span className="font-mono text-text-primary">
                {workspace.slug}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-text-muted">ID</span>
              <span className="font-mono text-text-muted">{workspace.id}</span>
            </div>
          </div>
        </Card>

        {/* Coming soon */}
        <Card>
          <CardHeader title="API Keys" />
          <p className="text-sm text-text-muted">
            API key management is coming soon.
          </p>
        </Card>

        <Card>
          <CardHeader title="Members" />
          <p className="text-sm text-text-muted">
            Team member management is coming soon.
          </p>
        </Card>
      </div>
    </div>
  );
}
