from pydantic import BaseModel, Field


class UserPreferencesDTO(BaseModel):
    """User UI preferences. Not a domain concern — simple operational metadata."""

    theme: str = Field(default="light")
    sidebar_collapsed: bool = Field(default=False)
    dev_mode: bool = Field(default=False)
    default_scope: str = Field(default="workspace")
    font_family: str = Field(default="plex")


class UpdatePreferencesRequest(BaseModel):
    """Partial update — only set fields are applied."""

    theme: str | None = None
    sidebar_collapsed: bool | None = None
    dev_mode: bool | None = None
    default_scope: str | None = None
    font_family: str | None = None


class SearchHistoryEntry(BaseModel):
    query_text: str
    search_mode: str
    result_count: int | None = None
    created_at: str


class RecentDocumentEntry(BaseModel):
    artifact_id: str
    artifact_title: str | None = None
    created_at: str


class RecordSearchActivityRequest(BaseModel):
    query_text: str
    search_mode: str = "hierarchical"
    result_count: int | None = None


class RecordDocumentOpenRequest(BaseModel):
    artifact_id: str
    artifact_title: str | None = None
