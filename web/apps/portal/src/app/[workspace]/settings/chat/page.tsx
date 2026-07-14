"use client";

import { Globe, Lock } from "lucide-react";

import { Card, CardHeader } from "@/components/ui/Card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { ReasoningSettings } from "@/components/chat/ReasoningSettings";
import { useScopeStore } from "@/lib/stores/scope-store";

const SCOPE_OPTIONS = [
  { label: "Workspace", value: "workspace" as const, icon: Globe },
  { label: "Private", value: "private" as const, icon: Lock },
];

export default function ChatSettingsPage() {
  const { defaultScope, setDefaultScope } = useScopeStore();

  return (
    <div className="max-w-2xl space-y-6">
      <ReasoningSettings />

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
    </div>
  );
}
