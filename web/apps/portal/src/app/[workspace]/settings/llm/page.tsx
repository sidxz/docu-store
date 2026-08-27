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
        description="This DocuStore uses a shared AI provider. There is nothing to set up here."
      />
    );
  }

  return (
    <div className="max-w-2xl">
      <SettingsSectionHeader
        title="AI Provider"
        subtitle="Uploads and chat use your own AI provider account. Your key is encrypted and never shown again."
      />
      <Card>
        <LlmProviderForm />
      </Card>
    </div>
  );
}
