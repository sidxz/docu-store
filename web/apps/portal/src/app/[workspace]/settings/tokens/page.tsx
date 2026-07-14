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

/** Parse the shared limit input: "" = unlimited (null), else a non-negative int. */
function parseLimitInput(raw: string): number | null | undefined {
  if (raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isInteger(n) && n >= 0 ? n : undefined;
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
  const parsed = parseLimitInput(value);
  return (
    <span className="flex items-center gap-2">
      <input
        type="number"
        min={0}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        className="w-32 rounded-md border border-border-default bg-surface-elevated px-2 py-1 font-mono text-xs text-text-primary"
      />
      <button
        onClick={() => {
          if (parsed !== undefined) {
            onSave(parsed);
            setValue("");
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
  const usage = useMemberUsageStats("month");
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
        {members.isLoading || limits.isLoading ? (
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
                      {formatTokens(usageByUser.get(userId) ?? 0)}
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
            </tbody>
          </table>
        )}
        {(setUser.isError || clearUser.isError) && (
          <p className="mt-2 text-xs text-red-500">
            {setUser.error?.message ?? clearUser.error?.message}
          </p>
        )}
        <p className="mt-3 text-xs text-text-muted">
          Member list is capped at 50 (same as the stats member card). Setting a member's
          override to empty saves an explicit Unlimited that beats the workspace default.
        </p>
      </Card>
    </div>
  );
}
