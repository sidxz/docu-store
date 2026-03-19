export interface TagCategoryDTO {
  entity_type: string;
  display_name: string;
  artifact_count: number;
  distinct_count: number;
}

export interface TagFolderDTO {
  tag_value: string;
  display_name: string;
  artifact_count: number;
  has_children: boolean;
}

export interface BrowseCategoriesResponse {
  categories: TagCategoryDTO[];
  total_artifacts: number;
}

export interface BrowseFoldersResponse {
  entity_type: string;
  parent: string | null;
  folders: TagFolderDTO[];
  total_folders: number;
}

export interface ArtifactBrowseItemDTO {
  artifact_id: string;
  title: string | null;
  source_filename: string | null;
  artifact_type: string;
  page_count: number;
  presentation_date: string | null;
  author_names: string[];
}
