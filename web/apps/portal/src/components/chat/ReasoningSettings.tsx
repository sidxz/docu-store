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
  { key: "retrieval" as const, label: "Retrieval" },
  { key: "base" as const, label: "Base" },
];

export function ReasoningSettings() {
  const { reasoningDefaults, setReasoningDefault } = useChatStore();

  return (
    <Card>
      <CardHeader title="Advanced Reasoning" />
      <p className="mb-4 text-xs text-text-muted">
        Synthesis (answer) reasoning is controlled per message in chat via the Reasoning toggle —
        on by default in Deep Research. These advanced knobs tune the retrieval agent and the
        base/quick-mode model — they affect cost/latency/quality and aren&rsquo;t shown in chat. On
        local Ollama reasoning is on/off; effort levels apply to cloud providers.
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
