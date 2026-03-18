"use client";

import { Settings, Sun, Moon, Globe, Lock, Plug, CheckCircle } from "lucide-react";
import { ProgressSpinner } from "primereact/progressspinner";
import { SelectButton } from "primereact/selectbutton";

import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardHeader } from "@/components/ui/Card";
import { useThemeStore } from "@/lib/stores/theme-store";
import { useScopeStore } from "@/lib/stores/scope-store";
import { useSession } from "@/lib/auth";
import { usePlugins } from "@/plugins";

const THEME_OPTIONS = [
  { label: "Light", value: "light" as const },
  { label: "Dark", value: "dark" as const },
];

const SCOPE_OPTIONS = [
  { label: "Workspace", value: "workspace" as const },
  { label: "Private", value: "private" as const },
];

export default function SettingsPage() {
  const { theme, setTheme } = useThemeStore();
  const { defaultScope, setDefaultScope } = useScopeStore();
  const { workspace } = useSession();
  const { plugins, isLoading: pluginsLoading } = usePlugins();

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
          <SelectButton
            value={theme}
            options={THEME_OPTIONS}
            onChange={(e) => {
              if (e.value) setTheme(e.value);
            }}
            itemTemplate={(option) => (
              <span className="flex items-center gap-2">
                {option.value === "light" ? (
                  <Sun className="h-4 w-4" />
                ) : (
                  <Moon className="h-4 w-4" />
                )}
                {option.label}
              </span>
            )}
          />
        </Card>

        {/* Default Visibility */}
        <Card>
          <CardHeader title="Default Visibility" />
          <p className="mb-3 text-xs text-text-muted">
            New documents will be created with this visibility by default.
          </p>
          <SelectButton
            value={defaultScope}
            options={SCOPE_OPTIONS}
            onChange={(e) => {
              if (e.value) setDefaultScope(e.value);
            }}
            itemTemplate={(option) => (
              <span className="flex items-center gap-2">
                {option.value === "workspace" ? (
                  <Globe className="h-4 w-4" />
                ) : (
                  <Lock className="h-4 w-4" />
                )}
                {option.label}
              </span>
            )}
          />
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

        {/* Plugins */}
        <Card>
          <CardHeader title="Plugins" />
          {pluginsLoading ? (
            <div className="flex items-center gap-2 py-2">
              <ProgressSpinner
                style={{ width: "1.25rem", height: "1.25rem" }}
                strokeWidth="3"
              />
              <span className="text-sm text-text-muted">Loading plugins…</span>
            </div>
          ) : plugins.length === 0 ? (
            <p className="text-sm text-text-muted">No plugins enabled.</p>
          ) : (
            <div className="space-y-3">
              {plugins.map((p) => (
                <div
                  key={p.name}
                  className="flex items-start gap-3 rounded-lg border border-border-default bg-surface-elevated px-3 py-2.5"
                >
                  <Plug className="mt-0.5 h-4 w-4 shrink-0 text-text-muted" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-text-primary">
                        {p.name.replace(/_/g, " ")}
                      </span>
                      <span className="font-mono text-xs text-text-muted">
                        v{p.version}
                      </span>
                    </div>
                    {p.description && (
                      <p className="mt-0.5 text-xs text-text-muted">
                        {p.description}
                      </p>
                    )}
                  </div>
                  <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-ds-success" />
                </div>
              ))}
            </div>
          )}
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
