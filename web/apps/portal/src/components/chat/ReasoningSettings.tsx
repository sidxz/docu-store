"use client";

import { SelectButton } from "primereact/selectbutton";

import { Card, CardHeader } from "@/components/ui/Card";
import { useChatStore, type ReasoningDefault } from "@/lib/stores/chat-store";

const LEVEL_OPTIONS: { label: string; value: ReasoningDefault }[] = [
  { label: "Inherit (server default)", value: "inherit" },
  { label: "Off", value: "off" },
  { label: "Low", value: "low" },
  { label: "Medium", value: "medium" },
  { label: "High", value: "high" },
];

const LANES = [
  { key: "synthesis" as const, label: "Synthesis" },
  { key: "retrieval" as const, label: "Retrieval" },
  { key: "base" as const, label: "Base" },
];

export function ReasoningSettings() {
  const { reasoningDefaults, setReasoningDefault } = useChatStore();

  return (
    <Card>
      <CardHeader title="Reasoning Defaults" />
      <p className="mb-4 text-xs text-text-muted">
        Only synthesis reasoning is shown in chat (the Reasoning panel); retrieval and base affect
        cost/latency/quality. On local Ollama models reasoning is on/off — levels above &ldquo;off&rdquo; are
        equivalent; effort levels apply to cloud providers.
      </p>
      <div className="space-y-4">
        {LANES.map(({ key, label }) => (
          <div key={key} className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-4">
            <span className="w-20 shrink-0 text-sm text-text-primary">{label}</span>
            <SelectButton
              value={reasoningDefaults[key]}
              options={LEVEL_OPTIONS}
              onChange={(e) => {
                if (e.value) setReasoningDefault(key, e.value as ReasoningDefault);
              }}
            />
          </div>
        ))}
      </div>
    </Card>
  );
}
