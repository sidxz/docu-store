"use client";

import { KeyRound } from "lucide-react";

import { LlmProviderForm } from "@/components/settings/LlmProviderForm";
import { SettingsSectionHeader } from "@/components/settings/SettingsSectionHeader";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { useLlmProvider } from "@/hooks/use-llm-provider";

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
    <div className="max-w-2xl">
      <SettingsSectionHeader
        title="AI Provider"
        subtitle="Connect your own AI provider for document processing and chat."
      />
      <Card>
        <LlmProviderForm />
      </Card>
    </div>
  );
}
