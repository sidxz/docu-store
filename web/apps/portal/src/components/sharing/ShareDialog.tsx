"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Share2,
  Globe,
  Lock,
  UserPlus,
  Users,
  User,
  Loader2,
  Plus,
  Trash2,
} from "lucide-react";
import type { ResourceShare } from "@docu-store/types";
import type { WorkspaceMember, GroupInfo } from "@sentinel-auth/js";
import {
  useArtifactPermissions,
  useShareArtifact,
  useRevokeShare,
  useUpdateVisibility,
} from "@/hooks/use-permissions";
import { usePointerDrag } from "@/hooks/use-pointer-drag";
import { apiClient } from "@docu-store/api-client";
import { getInitials } from "@/lib/utils";
import { severityToVariant } from "@/lib/severity";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const PERMISSION_OPTIONS = [
  { label: "View", value: "view" as const },
  { label: "Edit", value: "edit" as const },
];

const GRANTEE_TYPE_OPTIONS = [
  { label: "User", value: "user" as const, icon: User },
  { label: "Group", value: "group" as const, icon: Users },
];

interface ShareDialogProps {
  artifactId: string;
  isOwnerOrAdmin: boolean;
}

export function ShareDialog({ artifactId, isOwnerOrAdmin }: ShareDialogProps) {
  const [visible, setVisible] = useState(false);
  const drag = usePointerDrag();

  const { data: acl, isLoading } = useArtifactPermissions(artifactId);
  const shareMutation = useShareArtifact();
  const revokeMutation = useRevokeShare();
  const visibilityMutation = useUpdateVisibility();

  // Grantee type toggle
  const [granteeType, setGranteeType] = useState<"user" | "group">("user");

  // User combobox state
  const [selectedMember, setSelectedMember] = useState<
    WorkspaceMember | undefined
  >(undefined);
  const [memberOpen, setMemberOpen] = useState(false);
  const [memberQuery, setMemberQuery] = useState("");
  const [memberSuggestions, setMemberSuggestions] = useState<WorkspaceMember[]>([]);
  const memberDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Group combobox state
  const [selectedGroup, setSelectedGroup] = useState<GroupInfo | undefined>(
    undefined,
  );
  const [groupOpen, setGroupOpen] = useState(false);
  const [groupQuery, setGroupQuery] = useState("");
  const [groupOptions, setGroupOptions] = useState<GroupInfo[]>([]);
  const [groupsLoaded, setGroupsLoaded] = useState(false);

  const [permission, setPermission] = useState<"view" | "edit">("view");

  const isWorkspaceVisible = acl?.visibility === "workspace";

  // Debounced server-side member search — house style (200ms), same endpoint/contract as before.
  useEffect(() => {
    const q = memberQuery.trim();
    if (memberDebounceRef.current) clearTimeout(memberDebounceRef.current);

    if (q.length < 2) {
      setMemberSuggestions([]);
      return;
    }

    memberDebounceRef.current = setTimeout(async () => {
      try {
        const { data, error } = await apiClient.GET("/workspace/members", {
          params: { query: { q, limit: 10 } },
        });
        if (error) throw new Error("Search failed");
        // Schema type doesn't overlap with Sentinel SDK types — double cast needed
        setMemberSuggestions((data as unknown as WorkspaceMember[]) ?? []);
      } catch {
        setMemberSuggestions([]);
      }
    }, 200);

    return () => {
      if (memberDebounceRef.current) clearTimeout(memberDebounceRef.current);
    };
  }, [memberQuery]);

  const loadGroups = async () => {
    if (groupsLoaded) return;
    try {
      const { data, error } = await apiClient.GET("/workspace/groups");
      if (error) throw new Error("Failed to load groups");
      // Schema type doesn't overlap with Sentinel SDK types — double cast needed
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
      toast.success("Shared", { description: `Access granted to ${granteeName}` });
    } catch {
      toast.error("Failed", { description: "Could not share artifact" });
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
      toast.success("Revoked", {
        description: `Access removed for ${share.grantee_name ?? share.grantee_id}`,
      });
    } catch {
      toast.error("Failed", { description: "Could not revoke access" });
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
      toast.error("Failed", { description: "Could not update visibility" });
    }
  };

  const memberTemplate = (member: WorkspaceMember) => (
    <div className="flex flex-1 items-center gap-3 py-1">
      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-accent/10 text-xs font-medium text-accent-text">
        {getInitials(member.name)}
      </div>
      <div>
        <p className="text-sm font-medium">{member.name}</p>
        <p className="text-xs text-text-muted">{member.email}</p>
      </div>
    </div>
  );

  const groupItemTemplate = (option: GroupInfo) => (
    <div className="flex flex-1 items-center gap-3">
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
    <Dialog
      open={visible}
      onOpenChange={(open) => {
        setVisible(open);
        if (!open) drag.reset();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">
          <Share2 className="h-4 w-4" />
          Share
        </Button>
      </DialogTrigger>

      <DialogContent style={drag.style} className="sm:max-w-[480px]">
        <DialogHeader
          onPointerDown={drag.onPointerDown}
          className="cursor-move select-none"
        >
          <DialogTitle>Sharing &amp; Permissions</DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <LoadingSpinner size="sm" className="flex items-center justify-center py-8" />
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
                    <Label
                      htmlFor="visibility-toggle"
                      className="text-sm font-medium text-text-primary"
                    >
                      {isWorkspaceVisible ? "Workspace visible" : "Private"}
                    </Label>
                    <p className="text-xs text-text-muted">
                      {isWorkspaceVisible
                        ? "All workspace members can access"
                        : "Only shared users can access"}
                    </p>
                  </div>
                </div>
                <Switch
                  id="visibility-toggle"
                  checked={isWorkspaceVisible}
                  onCheckedChange={handleVisibilityToggle}
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
                  <ToggleGroup
                    type="single"
                    variant="outline"
                    size="sm"
                    value={granteeType}
                    onValueChange={(nv) => {
                      if (nv) {
                        setGranteeType(nv as "user" | "group");
                        setSelectedMember(undefined);
                        setSelectedGroup(undefined);
                      }
                    }}
                  >
                    {GRANTEE_TYPE_OPTIONS.map((option) => (
                      <ToggleGroupItem
                        key={option.value}
                        value={option.value}
                        className="gap-1.5 text-xs"
                      >
                        <option.icon className="h-3.5 w-3.5" />
                        {option.label}
                      </ToggleGroupItem>
                    ))}
                  </ToggleGroup>
                </div>

                {/* Row 1: grantee picker */}
                <div className="mb-2">
                  {granteeType === "user" ? (
                    <Popover open={memberOpen} onOpenChange={setMemberOpen}>
                      <PopoverTrigger asChild>
                        <Button
                          variant="outline"
                          className="w-full justify-start font-normal"
                        >
                          {selectedMember ? (
                            selectedMember.name
                          ) : (
                            <span className="text-text-muted">
                              Search by name or email...
                            </span>
                          )}
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent
                        className="w-[var(--radix-popover-trigger-width)] p-0"
                        align="start"
                      >
                        <Command shouldFilter={false}>
                          <CommandInput
                            placeholder="Search by name or email..."
                            value={memberQuery}
                            onValueChange={setMemberQuery}
                          />
                          <CommandList>
                            <CommandEmpty>
                              {memberQuery.trim().length < 2
                                ? "Type at least 2 characters..."
                                : "No members found"}
                            </CommandEmpty>
                            {memberSuggestions.map((member) => (
                              <CommandItem
                                key={member.user_id}
                                value={member.user_id}
                                onSelect={() => {
                                  setSelectedMember(member);
                                  setMemberQuery("");
                                  setMemberOpen(false);
                                }}
                              >
                                {memberTemplate(member)}
                              </CommandItem>
                            ))}
                          </CommandList>
                        </Command>
                      </PopoverContent>
                    </Popover>
                  ) : (
                    <Popover
                      open={groupOpen}
                      onOpenChange={(open) => {
                        setGroupOpen(open);
                        if (open) loadGroups();
                        else setGroupQuery("");
                      }}
                    >
                      <PopoverTrigger asChild>
                        <Button
                          variant="outline"
                          className="w-full justify-start font-normal"
                        >
                          {selectedGroup ? (
                            selectedGroup.name
                          ) : (
                            <span className="text-text-muted">Select group...</span>
                          )}
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent
                        className="w-[var(--radix-popover-trigger-width)] p-0"
                        align="start"
                      >
                        <Command>
                          <CommandInput
                            placeholder="Search groups..."
                            value={groupQuery}
                            onValueChange={setGroupQuery}
                          />
                          <CommandList>
                            <CommandEmpty>
                              {groupsLoaded ? "No groups found" : "Loading..."}
                            </CommandEmpty>
                            {groupOptions.map((group) => (
                              <CommandItem
                                key={group.id}
                                value={group.name}
                                onSelect={() => {
                                  setSelectedGroup(group);
                                  setGroupQuery("");
                                  setGroupOpen(false);
                                }}
                              >
                                {groupItemTemplate(group)}
                              </CommandItem>
                            ))}
                          </CommandList>
                        </Command>
                      </PopoverContent>
                    </Popover>
                  )}
                </div>

                {/* Row 2: permission + add */}
                <div className="flex items-center gap-2">
                  <Select
                    value={permission}
                    onValueChange={(v) => setPermission(v as "view" | "edit")}
                  >
                    <SelectTrigger className="w-28">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PERMISSION_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    onClick={handleShare}
                    disabled={!hasSelection || shareMutation.isPending}
                  >
                    {shareMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Plus className="h-4 w-4" />
                    )}
                    Add
                  </Button>
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
                      {getInitials(acl.owner_name)}
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
                            {getInitials(share.grantee_name)}
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
                        <Badge
                          variant={
                            severityToVariant[
                              share.grantee_type === "group" ? "info" : "secondary"
                            ]
                          }
                          className="text-xs"
                        >
                          {share.grantee_type}
                        </Badge>
                        <span className="rounded-md bg-border-subtle px-2 py-0.5 text-xs font-medium text-text-secondary">
                          {share.permission}
                        </span>
                        {isOwnerOrAdmin && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="rounded-full text-destructive hover:bg-destructive/10 hover:text-destructive"
                                onClick={() => handleRevoke(share)}
                                disabled={revokeMutation.isPending}
                                aria-label="Revoke access"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent side="top">Revoke access</TooltipContent>
                          </Tooltip>
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
      </DialogContent>
    </Dialog>
  );
}
