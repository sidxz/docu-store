"use client";

import { useState } from "react";
import { AlertTriangle, ShieldAlert } from "lucide-react";
import { useAuthzHasRole } from "@sentinel-auth/react";

import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { useMemberUsageStats, useWorkspaceMembers } from "@/hooks/use-stats";
import {
  useClearUserTokenLimit,
  useSetDefaultTokenLimit,
  useSetUserTokenLimit,
  useWorkspaceTokenLimits,
} from "@/hooks/use-token-limits";
import { formatTokens } from "@/lib/utils";

function limitLabel(limit: number | null): string {
  return limit === null ? "Unlimited" : formatTokens(limit);
}

/** Parse the shared limit input: "" = unlimited (null), else a non-negative int.
 * Capped at MAX_SAFE_INTEGER — beyond that JS silently loses precision. */
function parseLimitInput(raw: string): number | null | undefined {
  if (raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isInteger(n) && n >= 0 && n <= Number.MAX_SAFE_INTEGER ? n : undefined;
}

function LimitInput({
  onSave,
  isPending,
  placeholder,
}: {
  onSave: (limit: number | null) => void;
  isPending: boolean;
  placeholder: string;
}) {
  const [value, setValue] = useState("");
  const [badInput, setBadInput] = useState(false);
  // badInput: the field shows text (e.g. "12e") but exposes value="" — without
  // this guard that would parse as "" = unlimited and silently drop the quota.
  const parsed = badInput ? undefined : parseLimitInput(value);
  return (
    <span className="flex items-center gap-2">
      <input
        type="number"
        min={0}
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          setBadInput(e.target.validity.badInput);
        }}
        placeholder={placeholder}
        className="w-32 rounded-md border border-border-default bg-surface-elevated px-2 py-1 font-mono text-xs text-text-primary"
      />
      <button
        onClick={() => {
          if (parsed !== undefined) {
            onSave(parsed);
            setValue("");
            setBadInput(false);
          }
        }}
        disabled={isPending || parsed === undefined}
        className="rounded-md border border-border-default px-2 py-1 text-xs text-text-primary hover:bg-surface-sunken disabled:opacity-50"
      >
        Set
      </button>
    </span>
  );
}

export default function TokenSettingsPage() {
  const isAdmin = useAuthzHasRole("admin");
  const limits = useWorkspaceTokenLimits();
  const members = useWorkspaceMembers();
  // No polling: usage here is context for editing limits, not a live dashboard.
  const usage = useMemberUsageStats("calendar_month", false);
  const setDefault = useSetDefaultTokenLimit();
  const setUser = useSetUserTokenLimit();
  const clearUser = useClearUserTokenLimit();

  if (!isAdmin) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Access Denied"
        description="You need admin privileges to manage token limits."
      />
    );
  }

  if (limits.isError || members.isError) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Failed to load token limits"
        description={
          (limits.error ?? members.error) instanceof Error
            ? (limits.error ?? members.error)!.message
            : "An unknown error occurred."
        }
      />
    );
  }

  const defaultLimit = limits.data?.default_limit ?? null;
  const overrideByUser = new Map(
    (limits.data?.overrides ?? []).map((o) => [o.user_id, o.limit]),
  );
  const usageByUser = new Map(
    (usage.data?.members ?? []).map((m) => [m.user_id, m.total_tokens]),
  );
  // Overrides still enforce even when their user isn't in the (capped) member
  // list — departed members or workspaces >50. Surface them so admins can clear.
  const memberIds = new Set((members.data ?? []).map((m) => m.user_id ?? m.id ?? ""));
  const orphanOverrides = (limits.data?.overrides ?? []).filter(
    (o) => !memberIds.has(o.user_id),
  );

  return (
    <div className="max-w-4xl space-y-6">
      <Card>
        <CardHeader title="Workspace Default" />
        <p className="mb-3 text-xs text-text-muted">
          Monthly token budget applied to every member without an override. Empty = unlimited.
          Usage resets on the 1st (UTC). Admins are exempt from enforcement.
        </p>
        <div className="flex items-center gap-4 text-sm">
          <span className="font-mono text-text-primary">{limitLabel(defaultLimit)}</span>
          <LimitInput
            onSave={(limit) => setDefault.mutate(limit)}
            isPending={setDefault.isPending}
            placeholder="e.g. 5000000"
          />
        </div>
        {setDefault.isError && (
          <p className="mt-2 text-xs text-red-500">{setDefault.error.message}</p>
        )}
      </Card>

      <Card>
        <CardHeader title="Member Limits" />
        {members.isLoading || limits.isLoading || usage.isLoading ? (
          <p className="text-sm text-text-muted">Loading members…</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-default text-left text-xs text-text-muted">
                <th className="py-2 font-medium">Member</th>
                <th className="py-2 font-medium">This month</th>
                <th className="py-2 font-medium">Limit</th>
                <th className="py-2 font-medium">Override</th>
              </tr>
            </thead>
            <tbody>
              {(members.data ?? []).map((m) => {
                const userId = m.user_id ?? m.id ?? "";
                const hasOverride = overrideByUser.has(userId);
                const effective = hasOverride ? overrideByUser.get(userId)! : defaultLimit;
                return (
                  <tr key={userId} className="border-b border-border-default/50">
                    <td className="py-2">
                      <div className="text-text-primary">{m.name ?? "Unknown"}</div>
                      <div className="text-xs text-text-muted">{m.email ?? userId}</div>
                    </td>
                    <td className="py-2 font-mono text-text-primary">
                      {usage.isError ? "—" : formatTokens(usageByUser.get(userId) ?? 0)}
                    </td>
                    <td className="py-2">
                      <span className="font-mono text-text-primary">
                        {limitLabel(effective)}
                      </span>{" "}
                      <span className="text-xs text-text-muted">
                        {hasOverride ? "override" : "default"}
                      </span>
                    </td>
                    <td className="py-2">
                      <span className="flex items-center gap-2">
                        <LimitInput
                          onSave={(limit) => setUser.mutate({ userId, limit })}
                          isPending={setUser.isPending}
                          placeholder="tokens"
                        />
                        {hasOverride && (
                          <button
                            onClick={() => clearUser.mutate(userId)}
                            disabled={clearUser.isPending}
                            className="text-xs text-text-muted underline hover:text-text-primary disabled:opacity-50"
                          >
                            Clear
                          </button>
                        )}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {orphanOverrides.map((o) => (
                <tr key={o.user_id} className="border-b border-border-default/50">
                  <td className="py-2">
                    <div className="text-text-primary">Unknown member</div>
                    <div className="text-xs text-text-muted">{o.user_id}</div>
                  </td>
                  <td className="py-2 font-mono text-text-primary">
                    {usage.isError ? "—" : formatTokens(usageByUser.get(o.user_id) ?? 0)}
                  </td>
                  <td className="py-2">
                    <span className="font-mono text-text-primary">{limitLabel(o.limit)}</span>{" "}
                    <span className="text-xs text-text-muted">override</span>
                  </td>
                  <td className="py-2">
                    <button
                      onClick={() => clearUser.mutate(o.user_id)}
                      disabled={clearUser.isPending}
                      className="text-xs text-text-muted underline hover:text-text-primary disabled:opacity-50"
                    >
                      Clear
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {(setUser.isError || clearUser.isError) && (
          <p className="mt-2 text-xs text-red-500">
            {setUser.error?.message ?? clearUser.error?.message}
          </p>
        )}
        <p className="mt-3 text-xs text-text-muted">
          Member list is capped at 50 (same as the stats member card); overrides for anyone
          not in it show as "Unknown member" so they can still be cleared. Setting a member's
          override to empty saves an explicit Unlimited that beats the workspace default.
        </p>
      </Card>
    </div>
  );
}
