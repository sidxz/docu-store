"use client";

import { useRef, useState } from "react";
import { Dialog } from "primereact/dialog";
import { InputText } from "primereact/inputtext";
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
import type { ResourceShare, ShareRequest } from "@docu-store/types";
import {
  useArtifactPermissions,
  useShareArtifact,
  useRevokeShare,
  useUpdateVisibility,
} from "@/hooks/use-permissions";

const PERMISSION_OPTIONS = [
  { label: "View", value: "view" as const },
  { label: "Edit", value: "edit" as const },
];

const GRANTEE_TYPE_OPTIONS = [
  { label: "User", value: "user" as const },
  { label: "Group", value: "group" as const },
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

  // Share form state
  const [granteeId, setGranteeId] = useState("");
  const [granteeType, setGranteeType] = useState<"user" | "group">("user");
  const [permission, setPermission] = useState<"view" | "edit">("view");

  const isWorkspaceVisible = acl?.visibility === "workspace";

  const handleShare = async () => {
    if (!granteeId.trim()) return;

    const share: ShareRequest = {
      grantee_type: granteeType,
      grantee_id: granteeId.trim(),
      permission,
    };

    try {
      await shareMutation.mutateAsync({ artifactId, share });
      setGranteeId("");
      toast.current?.show({
        severity: "success",
        summary: "Shared",
        detail: `Access granted to ${granteeType}`,
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
        detail: "Access removed",
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
                      {isWorkspaceVisible
                        ? "Workspace visible"
                        : "Private"}
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
                  <Dropdown
                    value={granteeType}
                    options={GRANTEE_TYPE_OPTIONS}
                    onChange={(e) => setGranteeType(e.value)}
                    className="w-28"
                  />
                  <InputText
                    value={granteeId}
                    onChange={(e) => setGranteeId(e.target.value)}
                    placeholder="User or group ID"
                    className="flex-1"
                    onKeyDown={(e) => e.key === "Enter" && handleShare()}
                  />
                  <Dropdown
                    value={permission}
                    options={PERMISSION_OPTIONS}
                    onChange={(e) => setPermission(e.value)}
                    className="w-24"
                  />
                  <button
                    onClick={handleShare}
                    disabled={!granteeId.trim() || shareMutation.isPending}
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

            {/* Current shares */}
            <div>
              <h4 className="mb-3 flex items-center gap-2 text-sm font-medium text-text-primary">
                <Users className="h-4 w-4" />
                Current access
              </h4>

              {/* Owner */}
              {acl?.owner_id && (
                <div className="flex items-center justify-between rounded-lg border border-border-default bg-surface-default px-4 py-3">
                  <div className="flex items-center gap-3">
                    <User className="h-4 w-4 text-text-muted" />
                    <div>
                      <p className="text-sm font-medium text-text-primary">
                        Owner
                      </p>
                      <p className="font-mono text-xs text-text-muted">
                        {acl.owner_id}
                      </p>
                    </div>
                  </div>
                  <span className="rounded-md bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent-text">
                    Full access
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
                          <Users className="h-4 w-4 text-text-muted" />
                        ) : (
                          <User className="h-4 w-4 text-text-muted" />
                        )}
                        <div>
                          <p className="text-sm text-text-primary">
                            <span className="capitalize">
                              {share.grantee_type}
                            </span>
                          </p>
                          <p className="font-mono text-xs text-text-muted">
                            {share.grantee_id}
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
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                !acl?.owner_id && (
                  <p className="py-4 text-center text-sm text-text-muted">
                    No shares configured.
                  </p>
                )
              )}

              {acl?.shares?.length === 0 && acl?.owner_id && (
                <p className="mt-2 py-2 text-center text-xs text-text-muted">
                  No additional shares.
                </p>
              )}
            </div>
          </div>
        )}
      </Dialog>
    </>
  );
}
