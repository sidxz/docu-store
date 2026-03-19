"""DTOs for tag-based document browsing."""

from uuid import UUID

from pydantic import BaseModel, Field


class TagCategoryDTO(BaseModel):
    """A tag entity type with aggregate counts across artifacts."""

    entity_type: str = Field(description="e.g. target, compound_name, author, date")
    display_name: str = Field(description="Human-readable label")
    artifact_count: int = Field(description="Artifacts with at least one tag of this type")
    distinct_count: int = Field(description="Unique tag values")


class TagFolderDTO(BaseModel):
    """A single tag value within a category, acting as a virtual folder."""

    tag_value: str = Field(description="Normalized value (lowercase, stripped)")
    display_name: str = Field(description="Original casing for display")
    artifact_count: int
    has_children: bool = Field(default=False, description="True for date-year folders")


class BrowseCategoriesResponse(BaseModel):
    """Top-level categories available for browsing."""

    categories: list[TagCategoryDTO]
    total_artifacts: int


class BrowseFoldersResponse(BaseModel):
    """Folders within a single category."""

    entity_type: str
    parent: str | None = None
    folders: list[TagFolderDTO]
    total_folders: int


class ArtifactBrowseItemDTO(BaseModel):
    """Lightweight artifact representation for folder listings."""

    artifact_id: UUID
    title: str | None = None
    source_filename: str | None = None
    artifact_type: str
    page_count: int
    presentation_date: str | None = Field(default=None, description="ISO formatted")
    author_names: list[str] = Field(default_factory=list)
