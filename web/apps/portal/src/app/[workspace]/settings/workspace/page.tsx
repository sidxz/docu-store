"use client";

import { Plug, CheckCircle, Loader2 } from "lucide-react";

import { Card, CardHeader } from "@/components/ui/Card";
import { useSession } from "@/lib/auth";
import { useAppConfig } from "@/lib/app-config";
import { inviteUrl } from "@/lib/onboard";
import { usePlugins } from "@/plugins";

export default function WorkspaceSettingsPage() {
  const { workspace } = useSession();
  const { duarUrl, selfServeEnabled } = useAppConfig();
  const { plugins, isLoading: pluginsLoading } = usePlugins();

  return (
    <div className="max-w-2xl space-y-6">
      <Card>
        <CardHeader title="Workspace" />
        <div className="space-y-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-text-muted">Name</span>
            <span className="text-text-primary">{workspace.name}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-muted">Slug</span>
            <span className="font-mono text-text-primary">{workspace.slug}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-muted">ID</span>
            <span className="font-mono text-text-muted">{workspace.id}</span>
          </div>
          {selfServeEnabled && (
            <div className="pt-1">
              <a
                href={inviteUrl(duarUrl, workspace.id)}
                className="text-sm underline"
                style={{ color: "#2563eb" }}
              >
                Invite people
              </a>
            </div>
          )}
        </div>
      </Card>

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
                    <span className="font-mono text-xs text-text-muted">v{p.version}</span>
                  </div>
                  {p.description && (
                    <p className="mt-0.5 text-xs text-text-muted">{p.description}</p>
                  )}
                </div>
                <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-ds-success" />
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="API Keys" />
        <p className="text-sm text-text-muted">API key management is coming soon.</p>
      </Card>
    </div>
  );
}
