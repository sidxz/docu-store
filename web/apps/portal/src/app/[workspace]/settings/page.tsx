"use client";

import { Settings, Sun, Moon, Globe, Lock, Plug, CheckCircle, Code, Loader2, Type } from "lucide-react";

import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardHeader } from "@/components/ui/Card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { ReasoningSettings } from "@/components/chat/ReasoningSettings";
import { useThemeStore } from "@/lib/stores/theme-store";
import { useScopeStore } from "@/lib/stores/scope-store";
import { useDevModeStore } from "@/lib/stores/dev-mode-store";
import { useFontFamilyStore } from "@/lib/stores/font-family-store";
import { useSession } from "@/lib/auth";
import { usePlugins } from "@/plugins";

const THEME_OPTIONS = [
  { label: "Light", value: "light" as const, icon: Sun },
  { label: "Dark", value: "dark" as const, icon: Moon },
];

const FONT_OPTIONS = [
  { label: "Overused Grotesk", value: "grotesk" as const, icon: Type },
  { label: "IBM Plex", value: "plex" as const, icon: Type },
  { label: "Inter", value: "inter" as const, icon: Type },
];

const SCOPE_OPTIONS = [
  { label: "Workspace", value: "workspace" as const, icon: Globe },
  { label: "Private", value: "private" as const, icon: Lock },
];

export default function SettingsPage() {
  const { theme, setTheme } = useThemeStore();
  const { defaultScope, setDefaultScope } = useScopeStore();
  const { enabled: devMode, setEnabled: setDevMode } = useDevModeStore();
  const { font, setFont } = useFontFamilyStore();
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
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={theme}
            onValueChange={(nv) => {
              if (nv) setTheme(nv as "light" | "dark");
            }}
          >
            {THEME_OPTIONS.map(({ value, label, icon: Icon }) => (
              <ToggleGroupItem key={value} value={value}>
                <span className="flex items-center gap-2">
                  <Icon className="h-4 w-4" />
                  {label}
                </span>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>

          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            className="mt-4"
            value={font}
            onValueChange={(nv) => {
              if (nv) setFont(nv as "plex" | "inter" | "grotesk");
            }}
          >
            {FONT_OPTIONS.map(({ value, label, icon: Icon }) => (
              <ToggleGroupItem key={value} value={value}>
                <span className="flex items-center gap-2">
                  <Icon className="h-4 w-4" />
                  {label}
                </span>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </Card>

        {/* Developer Mode */}
        <Card>
          <CardHeader title="Developer Mode" />
          <p className="mb-3 text-xs text-text-muted">
            Show debug overlays with scoring details, RRF breakdowns, and pipeline diagnostics across the UI.
          </p>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={devMode ? "on" : "off"}
            onValueChange={(nv) => {
              if (nv) setDevMode(nv === "on");
            }}
          >
            <ToggleGroupItem value="off">
              <span className="flex items-center gap-2">
                <Code className="h-4 w-4" />
                Off
              </span>
            </ToggleGroupItem>
            <ToggleGroupItem value="on">
              <span className="flex items-center gap-2">
                <Code className="h-4 w-4" />
                On
              </span>
            </ToggleGroupItem>
          </ToggleGroup>
        </Card>

        {/* Reasoning */}
        <ReasoningSettings />

        {/* Default Visibility */}
        <Card>
          <CardHeader title="Default Visibility" />
          <p className="mb-3 text-xs text-text-muted">
            New documents will be created with this visibility by default.
          </p>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={defaultScope}
            onValueChange={(nv) => {
              if (nv) setDefaultScope(nv as "workspace" | "private");
            }}
          >
            {SCOPE_OPTIONS.map(({ value, label, icon: Icon }) => (
              <ToggleGroupItem key={value} value={value}>
                <span className="flex items-center gap-2">
                  <Icon className="h-4 w-4" />
                  {label}
                </span>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
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
              <Loader2 className="size-5 animate-spin text-text-muted" />
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
