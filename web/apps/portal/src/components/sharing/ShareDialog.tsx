"use client";

import { useRef, useState } from "react";
import { Dialog } from "primereact/dialog";
import { AutoComplete } from "primereact/autocomplete";
import { Dropdown } from "primereact/dropdown";
import { InputSwitch } from "primereact/inputswitch";
import { Toast } from "primereact/toast";
import {
  Share2,
  Trash2,
  Loader2,
  Globe,
  Lock,
  UserPlus,
  Users,
  User,
} from "lucide-react";
import type { ResourceShare, WorkspaceMember } from "@docu-store/types";
import {
  useArtifactPermissions,
  useShareArtifact,
  useRevokeShare,
  useUpdateVisibility,
} from "@/hooks/use-permissions";
import { getAuthzClient } from "@/lib/authz-client";

const PERMISSION_OPTIONS = [
  { label: "View", value: "view" as const },
  { label: "Edit", value: "edit" as const },
];

interface ShareDialogProps {
  artifactId: string;
  isOwnerOrAdmin: boolean;
}

export function ShareDialog({ artifactId, isOwnerOrAdmin }: ShareDialogProps) {
  const [visible, setVisible] = useState(false);
  const toast = useRef<Toast>(null);

  const { data: acl, isLoading } = useArtifactPermissions(artifactId);
  const shareMutation = useShareArtifact();
  const revokeMutation = useRevokeShare();
  const visibilityMutation = useUpdateVisibility();

  // Autocomplete state
  const [selectedMember, setSelectedMember] = useState<
    WorkspaceMember | undefined
  >(undefined);
  const [suggestions, setSuggestions] = useState<WorkspaceMember[]>([]);
  const [permission, setPermission] = useState<"view" | "edit">("view");

  const isWorkspaceVisible = acl?.visibility === "workspace";

  const searchMembers = async (event: { query: string }) => {
    if (event.query.length < 2) {
      setSuggestions([]);
      return;
    }
    try {
      // searchMembers() added in @sentinel-auth/js 0.9.7
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const client = getAuthzClient() as any;
      const results = (await client.searchMembers(
        event.query,
        10,
      )) as WorkspaceMember[];
      setSuggestions(results);
    } catch {
      setSuggestions([]);
    }
  };

  const handleShare = async () => {
    if (!selectedMember) return;

    try {
      await shareMutation.mutateAsync({
        artifactId,
        share: {
          grantee_type: "user",
          grantee_id: selectedMember.user_id,
          permission,
        },
      });
      setSelectedMember(undefined);
      toast.current?.show({
        severity: "success",
        summary: "Shared",
        detail: `Access granted to ${selectedMember.name}`,
        life: 3000,
      });
    } catch {
      toast.current?.show({
        severity: "error",
        summary: "Failed",
        detail: "Could not share artifact",
        life: 3000,
      });
    }
  };

  const handleRevoke = async (share: ResourceShare) => {
    try {
      await revokeMutation.mutateAsync({
        artifactId,
        share: {
          grantee_type: share.grantee_type,
          grantee_id: share.grantee_id,
          permission: share.permission,
        },
      });
      toast.current?.show({
        severity: "success",
        summary: "Revoked",
        detail: `Access removed for ${share.grantee_name ?? share.grantee_id}`,
        life: 3000,
      });
    } catch {
      toast.current?.show({
        severity: "error",
        summary: "Failed",
        detail: "Could not revoke access",
        life: 3000,
      });
    }
  };

  const handleVisibilityToggle = async (checked: boolean) => {
    const newVisibility = checked ? "workspace" : "private";
    try {
      await visibilityMutation.mutateAsync({
        artifactId,
        visibility: newVisibility,
      });
    } catch {
      toast.current?.show({
        severity: "error",
        summary: "Failed",
        detail: "Could not update visibility",
        life: 3000,
      });
    }
  };

  const memberTemplate = (member: WorkspaceMember) => (
    <div className="flex items-center gap-3 py-1">
      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-accent/10 text-xs font-medium text-accent-text">
        {member.name
          .split(" ")
          .map((n) => n[0])
          .join("")
          .slice(0, 2)
          .toUpperCase()}
      </div>
      <div>
        <p className="text-sm font-medium">{member.name}</p>
        <p className="text-xs text-text-muted">{member.email}</p>
      </div>
    </div>
  );

  return (
    <>
      <Toast ref={toast} />
      <button
        onClick={() => setVisible(true)}
        className="flex items-center gap-2 rounded-lg border border-border-default px-3 py-2 text-sm text-text-secondary transition-colors hover:bg-surface-elevated"
      >
        <Share2 className="h-4 w-4" />
        Share
      </button>

      <Dialog
        header="Sharing & Permissions"
        visible={visible}
        onHide={() => setVisible(false)}
        style={{ width: "480px" }}
        modal
        draggable={false}
      >
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-accent" />
          </div>
        ) : (
          <div className="space-y-6">
            {/* Visibility toggle */}
            {isOwnerOrAdmin && (
              <div className="flex items-center justify-between rounded-lg border border-border-default bg-surface-default p-4">
                <div className="flex items-center gap-3">
                  {isWorkspaceVisible ? (
                    <Globe className="h-5 w-5 text-ds-success" />
                  ) : (
                    <Lock className="h-5 w-5 text-text-muted" />
                  )}
                  <div>
                    <p className="text-sm font-medium text-text-primary">
                      {isWorkspaceVisible ? "Workspace visible" : "Private"}
                    </p>
                    <p className="text-xs text-text-muted">
                      {isWorkspaceVisible
                        ? "All workspace members can access"
                        : "Only shared users can access"}
                    </p>
                  </div>
                </div>
                <InputSwitch
                  checked={isWorkspaceVisible}
                  onChange={(e) => handleVisibilityToggle(e.value ?? false)}
                  disabled={visibilityMutation.isPending}
                />
              </div>
            )}

            {/* Add share form */}
            {isOwnerOrAdmin && (
              <div>
                <h4 className="mb-3 flex items-center gap-2 text-sm font-medium text-text-primary">
                  <UserPlus className="h-4 w-4" />
                  Share with
                </h4>
                <div className="flex gap-2">
                  <AutoComplete
                    value={selectedMember}
                    suggestions={suggestions}
                    completeMethod={searchMembers}
                    field="name"
                    itemTemplate={memberTemplate}
                    selectedItemTemplate={(m: WorkspaceMember) => m.name}
                    onChange={(e) => setSelectedMember(e.value)}
                    placeholder="Search by name or email..."
                    className="flex-1"
                    inputClassName="w-full"
                    minLength={2}
                    delay={300}
                    forceSelection
                  />
                  <Dropdown
                    value={permission}
                    options={PERMISSION_OPTIONS}
                    onChange={(e) => setPermission(e.value)}
                    className="w-24"
                  />
                  <button
                    onClick={handleShare}
                    disabled={!selectedMember || shareMutation.isPending}
                    className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/90 disabled:opacity-50"
                  >
                    {shareMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      "Add"
                    )}
                  </button>
                </div>
              </div>
            )}

            {/* Current access */}
            <div>
              <h4 className="mb-3 flex items-center gap-2 text-sm font-medium text-text-primary">
                <Users className="h-4 w-4" />
                Current access
              </h4>

              {/* Owner */}
              {acl?.owner_id && (
                <div className="flex items-center justify-between rounded-lg border border-border-default bg-surface-default px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent/10 text-xs font-medium text-accent-text">
                      {(acl.owner_name ?? "?")
                        .split(" ")
                        .map((n) => n[0])
                        .join("")
                        .slice(0, 2)
                        .toUpperCase()}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-text-primary">
                        {acl.owner_name ?? "Owner"}
                      </p>
                      <p className="text-xs text-text-muted">
                        {acl.owner_email ?? acl.owner_id}
                      </p>
                    </div>
                  </div>
                  <span className="rounded-md bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent-text">
                    Owner
                  </span>
                </div>
              )}

              {/* Shares list */}
              {acl?.shares && acl.shares.length > 0 ? (
                <div className="mt-2 space-y-2">
                  {acl.shares.map((share) => (
                    <div
                      key={`${share.grantee_type}-${share.grantee_id}-${share.permission}`}
                      className="flex items-center justify-between rounded-lg border border-border-default bg-surface-default px-4 py-3"
                    >
                      <div className="flex items-center gap-3">
                        {share.grantee_type === "group" ? (
                          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-border-subtle">
                            <Users className="h-4 w-4 text-text-muted" />
                          </div>
                        ) : (
                          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-border-subtle text-xs font-medium text-text-secondary">
                            {(share.grantee_name ?? "?")
                              .split(" ")
                              .map((n) => n[0])
                              .join("")
                              .slice(0, 2)
                              .toUpperCase()}
                          </div>
                        )}
                        <div>
                          <p className="text-sm font-medium text-text-primary">
                            {share.grantee_name ?? (
                              <span className="font-mono text-xs">
                                {share.grantee_id}
                              </span>
                            )}
                          </p>
                          <p className="text-xs text-text-muted">
                            {share.grantee_email ??
                              `${share.grantee_type}`}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="rounded-md bg-border-subtle px-2 py-0.5 text-xs font-medium text-text-secondary">
                          {share.permission}
                        </span>
                        {isOwnerOrAdmin && (
                          <button
                            onClick={() => handleRevoke(share)}
                            disabled={revokeMutation.isPending}
                            className="rounded p-1 text-text-muted transition-colors hover:bg-ds-error/10 hover:text-ds-error"
                            title="Revoke access"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                acl?.owner_id && (
                  <p className="mt-2 py-2 text-center text-xs text-text-muted">
                    No additional shares.
                  </p>
                )
              )}
            </div>
          </div>
        )}
      </Dialog>
    </>
  );
}
