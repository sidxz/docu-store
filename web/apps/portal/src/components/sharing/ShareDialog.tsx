"use client";

import { useRef, useState } from "react";
import { Dialog } from "primereact/dialog";
import { AutoComplete } from "primereact/autocomplete";
import { Button } from "primereact/button";
import { Dropdown } from "primereact/dropdown";
import { InputSwitch } from "primereact/inputswitch";
import { ProgressSpinner } from "primereact/progressspinner";
import { SelectButton } from "primereact/selectbutton";
import { Tag } from "primereact/tag";
import { Toast } from "primereact/toast";
import {
  Share2,
  Globe,
  Lock,
  UserPlus,
  Users,
  User,
} from "lucide-react";
import type { ResourceShare } from "@docu-store/types";
import type { WorkspaceMember, GroupInfo } from "@sentinel-auth/js";
import {
  useArtifactPermissions,
  useShareArtifact,
  useRevokeShare,
  useUpdateVisibility,
} from "@/hooks/use-permissions";
import { apiClient } from "@docu-store/api-client";

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

  // Grantee type toggle
  const [granteeType, setGranteeType] = useState<"user" | "group">("user");

  // User autocomplete state
  const [selectedMember, setSelectedMember] = useState<
    WorkspaceMember | undefined
  >(undefined);
  const [memberSuggestions, setMemberSuggestions] = useState<WorkspaceMember[]>([]);

  // Group dropdown state
  const [selectedGroup, setSelectedGroup] = useState<GroupInfo | undefined>(
    undefined,
  );
  const [groupOptions, setGroupOptions] = useState<GroupInfo[]>([]);
  const [groupsLoaded, setGroupsLoaded] = useState(false);

  const [permission, setPermission] = useState<"view" | "edit">("view");

  const isWorkspaceVisible = acl?.visibility === "workspace";

  const searchMembers = async (event: { query: string }) => {
    if (event.query.length < 2) {
      setMemberSuggestions([]);
      return;
    }
    try {
      const { data, error } = await apiClient.GET("/workspace/members", {
        params: { query: { q: event.query, limit: 10 } },
      });
      if (error) throw new Error("Search failed");
      setMemberSuggestions((data as unknown as WorkspaceMember[]) ?? []);
    } catch {
      setMemberSuggestions([]);
    }
  };

  const loadGroups = async () => {
    if (groupsLoaded) return;
    try {
      const { data, error } = await apiClient.GET("/workspace/groups");
      if (error) throw new Error("Failed to load groups");
      setGroupOptions((data as unknown as GroupInfo[]) ?? []);
      setGroupsLoaded(true);
    } catch {
      setGroupOptions([]);
    }
  };

  const handleShare = async () => {
    if (granteeType === "user" && !selectedMember) return;
    if (granteeType === "group" && !selectedGroup) return;

    const granteeId =
      granteeType === "user" ? selectedMember!.user_id : selectedGroup!.id;
    const granteeName =
      granteeType === "user" ? selectedMember!.name : selectedGroup!.name;

    try {
      await shareMutation.mutateAsync({
        artifactId,
        share: {
          grantee_type: granteeType,
          grantee_id: granteeId,
          permission,
        },
      });
      setSelectedMember(undefined);
      setSelectedGroup(undefined);
      toast.current?.show({
        severity: "success",
        summary: "Shared",
        detail: `Access granted to ${granteeName}`,
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

  const groupItemTemplate = (option: GroupInfo) => (
    <div className="flex items-center gap-3">
      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-border-subtle">
        <Users className="h-3.5 w-3.5 text-text-muted" />
      </div>
      <div>
        <p className="text-sm font-medium">{option.name}</p>
        {option.description && (
          <p className="text-xs text-text-muted">{option.description}</p>
        )}
      </div>
    </div>
  );

  const hasSelection =
    granteeType === "user" ? !!selectedMember : !!selectedGroup;

  return (
    <>
      <Toast ref={toast} />
      <Button
        label="Share"
        icon={<Share2 className="h-4 w-4" />}
        onClick={() => setVisible(true)}
        outlined
        severity="secondary"
      />

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
            <ProgressSpinner
              style={{ width: "1.5rem", height: "1.5rem" }}
              strokeWidth="3"
            />
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

                {/* Grantee type selector */}
                <div className="mb-3">
                  <SelectButton
                    value={granteeType}
                    options={GRANTEE_TYPE_OPTIONS}
                    onChange={(e) => {
                      if (e.value) {
                        setGranteeType(e.value);
                        setSelectedMember(undefined);
                        setSelectedGroup(undefined);
                      }
                    }}
                    itemTemplate={(option) => (
                      <span className="flex items-center gap-1.5 text-xs">
                        {option.value === "user" ? (
                          <User className="h-3.5 w-3.5" />
                        ) : (
                          <Users className="h-3.5 w-3.5" />
                        )}
                        {option.label}
                      </span>
                    )}
                  />
                </div>

                {/* Row 1: grantee picker */}
                <div className="mb-2">
                  {granteeType === "user" ? (
                    <AutoComplete
                      value={selectedMember}
                      suggestions={memberSuggestions}
                      completeMethod={searchMembers}
                      field="name"
                      itemTemplate={memberTemplate}
                      selectedItemTemplate={(m: WorkspaceMember) => m.name}
                      onChange={(e) => setSelectedMember(e.value)}
                      placeholder="Search by name or email..."
                      className="w-full"
                      inputClassName="w-full"
                      minLength={2}
                      delay={300}
                      forceSelection
                    />
                  ) : (
                    <Dropdown
                      value={selectedGroup}
                      options={groupOptions}
                      optionLabel="name"
                      onChange={(e) => setSelectedGroup(e.value)}
                      onShow={loadGroups}
                      placeholder="Select group..."
                      className="w-full"
                      filter
                      filterBy="name"
                      itemTemplate={groupItemTemplate}
                      emptyMessage={groupsLoaded ? "No groups found" : "Loading..."}
                    />
                  )}
                </div>

                {/* Row 2: permission + add */}
                <div className="flex items-center gap-2">
                  <Dropdown
                    value={permission}
                    options={PERMISSION_OPTIONS}
                    onChange={(e) => setPermission(e.value)}
                    className="w-28"
                  />
                  <Button
                    label="Add"
                    onClick={handleShare}
                    disabled={!hasSelection || shareMutation.isPending}
                    loading={shareMutation.isPending}
                  />
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
                        <Tag
                          value={share.grantee_type}
                          severity={share.grantee_type === "group" ? "info" : "secondary"}
                          rounded
                          className="text-xs"
                        />
                        <span className="rounded-md bg-border-subtle px-2 py-0.5 text-xs font-medium text-text-secondary">
                          {share.permission}
                        </span>
                        {isOwnerOrAdmin && (
                          <Button
                            icon="pi pi-trash"
                            onClick={() => handleRevoke(share)}
                            disabled={revokeMutation.isPending}
                            severity="danger"
                            text
                            rounded
                            aria-label="Revoke access"
                            tooltip="Revoke access"
                            tooltipOptions={{ position: "top" }}
                          />
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
