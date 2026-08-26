from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


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


# ── BYO LLM provider ──────────────────────────────────────────────────────────

_Model = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class LLMProviderRequest(BaseModel):
    """PUT /user/llm-provider. Blank models fall back to the provider preset;
    omit ``api_key`` to change models only (the stored key is kept).
    """

    provider: Literal["openrouter", "openai", "gemini"]
    api_key: str | None = None
    model: _Model | None = None
    chat_model: _Model | None = None


class LLMProviderPreset(BaseModel):
    model: str
    chat_model: str


class LLMProviderResponse(BaseModel):
    """GET /user/llm-provider — the key is write-only; only its last 4 are shown."""

    enabled: bool
    configured: bool
    provider: str | None = None
    key_last4: str | None = None
    model: str | None = None
    chat_model: str | None = None
    presets: dict[str, LLMProviderPreset]


class LLMLaneTestResult(BaseModel):
    ok: bool
    detail: str | None = None


class LLMProviderTestResponse(BaseModel):
    ok: bool
    lanes: dict[str, LLMLaneTestResult]
