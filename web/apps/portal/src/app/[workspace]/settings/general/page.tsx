"use client";

import { Sun, Moon, Code, Type } from "lucide-react";

import { Card, CardHeader } from "@/components/ui/Card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useThemeStore } from "@/lib/stores/theme-store";
import { useDevModeStore } from "@/lib/stores/dev-mode-store";
import { useFontFamilyStore } from "@/lib/stores/font-family-store";

const THEME_OPTIONS = [
  { label: "Light", value: "light" as const, icon: Sun },
  { label: "Dark", value: "dark" as const, icon: Moon },
];

const FONT_OPTIONS = [
  { label: "Overused Grotesk", value: "grotesk" as const, icon: Type },
  { label: "IBM Plex", value: "plex" as const, icon: Type },
  { label: "Inter", value: "inter" as const, icon: Type },
];

export default function GeneralSettingsPage() {
  const { theme, setTheme } = useThemeStore();
  const { enabled: devMode, setEnabled: setDevMode } = useDevModeStore();
  const { font, setFont } = useFontFamilyStore();

  return (
    <div className="max-w-2xl space-y-6">
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
    </div>
  );
}
