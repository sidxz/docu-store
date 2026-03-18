/** Entity-level permission types (sharing, visibility). */

export interface ResourceShare {
  id: string;
  grantee_type: "user" | "group";
  grantee_id: string;
  grantee_name: string | null;
  grantee_email: string | null;
  permission: "view" | "edit";
  granted_by: string | null;
  granted_by_name: string | null;
  granted_at: string;
}

export interface ResourceACL {
  id: string;
  resource_type: string;
  resource_id: string;
  workspace_id: string;
  owner_id: string | null;
  owner_name: string | null;
  owner_email: string | null;
  visibility: "private" | "workspace";
  shares: ResourceShare[];
}

export interface ShareRequest {
  grantee_type: "user" | "group";
  grantee_id: string;
  permission: "view" | "edit";
}

export interface UpdateVisibilityRequest {
  visibility: "private" | "workspace";
}
