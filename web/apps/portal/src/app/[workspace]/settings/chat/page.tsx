"use client";

import { Globe, Lock } from "lucide-react";
import { toast } from "sonner";

import { Card, CardHeader } from "@/components/ui/Card";
import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { ReasoningSettings } from "@/components/chat/ReasoningSettings";
import { useSetAnswerFormatting, useWorkspaceChatSettings } from "@/hooks/use-workspace-chat-settings";
import { useScopeStore } from "@/lib/stores/scope-store";

const SCOPE_OPTIONS = [
  { label: "Workspace", value: "workspace" as const, icon: Globe },
  { label: "Private", value: "private" as const, icon: Lock },
];

export default function ChatSettingsPage() {
  const { defaultScope, setDefaultScope } = useScopeStore();

  return (
    <div className="max-w-2xl space-y-6">
      <AnswerFormattingSetting />
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

function AnswerFormattingSetting() {
  const { data } = useWorkspaceChatSettings();
  const setFormatting = useSetAnswerFormatting();
  if (!data) return null;

  return (
    <Card>
      <CardHeader
        title="Answer formatting"
        action={
          <Switch
            checked={data.answer_formatting}
            disabled={!data.can_manage || setFormatting.isPending}
            onCheckedChange={(on) =>
              setFormatting.mutate(on, {
                onError: () => toast.error("Could not update answer formatting"),
              })
            }
            aria-label="Answer formatting"
          />
        }
      />
      <p className="text-xs text-text-muted">
        A final pass that moves the part of each answer that most directly addresses the question
        to the top, leaving the rest as written. Turning it off shows the answer as drafted, which
        is faster and costs one model call less. Applies to everyone in this workspace.
        {!data.can_manage && " Only workspace admins can change it."}
      </p>
    </Card>
  );
}
