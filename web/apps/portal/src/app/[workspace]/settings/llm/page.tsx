"use client";

import { KeyRound } from "lucide-react";

import { EmbeddingModelCard } from "@/components/settings/EmbeddingModelCard";
import { LlmProviderForm } from "@/components/settings/LlmProviderForm";
import { SettingsSectionHeader } from "@/components/settings/SettingsSectionHeader";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { type LlmProviderStatus, useLlmProvider } from "@/hooks/use-llm-provider";

const PROVIDER_LABEL: Record<string, string> = {
  openai: "OpenAI",
  gemini: "Gemini",
  openrouter: "OpenRouter",
  tamu: "TAMU AI",
};

/** Members see what the workspace runs on; only admins connect or change keys. */
function WorkspaceProviderSummary({ data }: { data: LlmProviderStatus }) {
  const active = data.providers.find((p) => p.active);
  if (!active) {
    return (
      <p className="text-sm text-text-muted">
        No AI provider yet. Ask a workspace admin to connect one to enable document uploads and
        chat.
      </p>
    );
  }
  return (
    <div className="space-y-1 text-sm">
      <p className="font-medium text-text-primary">
        {PROVIDER_LABEL[active.provider] ?? active.provider}
      </p>
      <p className="text-text-muted">
        Documents: <span className="font-mono text-xs">{active.model}</span> · Chat:{" "}
        <span className="font-mono text-xs">{active.chat_model}</span>
      </p>
      <p className="text-xs text-text-muted">Managed by your workspace admins.</p>
    </div>
  );
}

export default function LlmProviderSettingsPage() {
  const { data } = useLlmProvider();

  if (data && !data.enabled) {
    return (
      <EmptyState
        icon={KeyRound}
        title="Not available"
        description="AI is already configured for this DocuStore. No setup is needed."
      />
    );
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <SettingsSectionHeader
          title="AI Provider"
          subtitle="The AI provider this workspace runs on, for document processing and chat."
        />
        <Card>
          {data && !data.can_manage ? <WorkspaceProviderSummary data={data} /> : <LlmProviderForm />}
        </Card>
      </div>
      <EmbeddingModelCard />
    </div>
  );
}
