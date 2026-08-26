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
        description="This deployment uses a shared LLM — there is nothing to configure here."
      />
    );
  }

  return (
    <div className="max-w-2xl">
      <SettingsSectionHeader
        title="AI Provider"
        subtitle="Uploads and chat run on your own model account. Your key is encrypted at rest and never shown again."
      />
      <Card>
        <LlmProviderForm />
      </Card>
    </div>
  );
}
