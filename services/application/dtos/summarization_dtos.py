from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PageSummarizationResponse(BaseModel):
    """Result of a successful page summarization."""

    page_id: UUID
    artifact_id: UUID
    summary: str
    model_name: str | None = None
    date_extracted: datetime | None = None
    is_locked: bool = False
